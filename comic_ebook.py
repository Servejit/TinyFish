"""Reusable TinyFish-powered comic e-book creation workflow for Streamlit."""

import json
import re
import time

import requests
import streamlit as st

SEARCH_URL = "https://api.search.tinyfish.ai"
AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
TIMEOUT = (20, 900)


def _valid_url(value):
    if not isinstance(value, str):
        return False
    return value.startswith("https://") or value.startswith("http://")


def _extract_urls(payload):
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in {"url", "link", "href", "website"} and isinstance(value, str):
                    candidate = value.strip().rstrip(".,)")
                    if _valid_url(candidate) and candidate not in seen:
                        seen.add(candidate)
                        found.append({
                            "url": candidate,
                            "title": str(node.get("title") or node.get("name") or "")[:250],
                            "snippet": str(node.get("snippet") or node.get("description") or "")[:500],
                        })
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def _discover_comic_sites(api_key, topic):
    query = (
        "online comic book creator illustrated storybook maker "
        "AI comic generator export or download PDF"
    )
    response = None
    retryable_statuses = {429, 500, 502, 503, 504}
    last_error = None

    # Search can temporarily return SERVICE_BUSY (HTTP 503). Retry a few times
    # before failing so a short provider outage does not immediately stop the workflow.
    for attempt in range(4):
        try:
            response = requests.get(
                SEARCH_URL,
                headers={"X-API-Key": api_key, "Accept": "application/json"},
                params={"query": query},
                timeout=40,
            )
            if response.status_code not in retryable_statuses:
                break
            last_error = (
                f"TinyFish Search returned HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )
        except requests.exceptions.RequestException as exc:
            last_error = f"TinyFish Search network error: {exc}"
            if attempt == 3:
                raise RuntimeError(last_error) from exc

        if attempt < 3:
            time.sleep(2 ** attempt)

    if response is None:
        raise RuntimeError(last_error or "TinyFish Search could not be reached.")
    if response.status_code >= 400:
        raise RuntimeError(
            (last_error or
             f"TinyFish Search returned HTTP {response.status_code}: {response.text[:1000]}")
            + " You can retry later or enter a website manually under Advanced option."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("TinyFish Search returned an invalid response.") from exc
    finally:
        response.close()

    candidates = _extract_urls(payload)
    if not candidates:
        raise RuntimeError(
            "TinyFish Search found no usable comic-book creation websites. "
            "Try again or enter a website in the optional website field."
        )

    preferred = (
        "comic", "storybook", "book", "design", "canva", "adobe",
        "illustration", "creator", "toon", "story",
    )
    for item in candidates:
        text = (item["url"] + " " + item["title"] + " " + item["snippet"]).lower()
        item["score"] = sum(3 for word in preferred if word in text)
        if "pdf" in text or "export" in text or "download" in text:
            item["score"] += 4
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return query, candidates[:8]


def _build_comic_goal(topic, chapters, audience, language, style, author, extra):
    author_text = author.strip() or "Author name to be added"
    extra_text = extra.strip() or "No additional instructions."
    return f"""
You are a professional illustrated comic e-book production assistant. Use the website
currently open in the browser to create a complete, original, colourful comic e-book.

PROJECT DETAILS
Topic: {topic}
Number of chapters/stories: {chapters}
Target audience: {audience}
Language: {language}
Illustration style: {style}
Author: {author_text}
Additional instructions: {extra_text}

CREATION REQUIREMENTS
1. Develop an engaging original e-book title and subtitle based on the topic.
2. Create {chapters} distinct chapters or stories that genuinely cover the requested topic.
3. Write complete stories, not outlines. Use memorable characters, different settings,
   meaningful conflicts, natural dialogue, emotional moments and satisfying endings.
4. Convert the stories into genuine illustrated comic pages with panels, speech bubbles,
   narration boxes and colourful original artwork. Do not substitute plain text pages
   with decorative borders for comic illustrations.
5. Keep characters visually consistent within each story. Make every chapter visually
   distinct while maintaining a coherent book design.
6. Use clear, age-appropriate language for the specified audience and write in {language}.
7. Include a professional cover, title page, copyright page with editable placeholders,
   introduction, table of contents, all chapters, closing page and author page.
8. Where appropriate, include a short lesson or takeaway and reflection questions at
   the end of each chapter.
9. Use a polished portrait book layout, readable typography, page numbers, balanced
   margins and high-resolution artwork.
10. Export the complete book as a downloadable PDF. Also create a separate cover image
    and a short product description if the website supports these outputs.

COMMERCIAL AND CONTENT RULES
- Create original stories and artwork, or use assets explicitly licensed for commercial use.
- Do not copy existing books, stories, illustrations, characters, logos or trademarks.
- Do not claim certifications, endorsements or awards that do not exist.
- Do not include watermarks or website branding in the finished book unless required
  by the site's legitimate free-tier export.
- Do not purchase anything, subscribe, start a paid trial, spend credits, or publish
  the book publicly. If a paid feature is required, stop and report the limitation.
- Do not bypass logins, CAPTCHA, paywalls or website security. If account sign-in is
  needed, stop and tell the user what manual step is required.

WORKFLOW
- Inspect the website and determine whether it can create illustrated comic books and
  export PDFs.
- If it cannot do the job, explain why. Do not pretend that it can.
- Use the website's available free/default features where possible.
- Work through the creation process. If the site has generation limits, create as much
  as it safely permits and clearly report what remains incomplete.
- Before finishing, verify that all {chapters} chapters are present, illustrations are
  included, text is readable, pages are not clipped or overlapping, and the PDF export
  exists.
- Obtain and return the actual PDF download URL and cover-image URL when available.
- Never invent a file, download link, completed chapter or successful export.

FINAL RESPONSE
Return a clear status (completed, partially completed or failed), the book title,
chapter count, page count if known, PDF download URL, cover URL, product description,
and any manual steps or limitations. A successful browser session alone does not mean
the e-book was successfully created.
""".strip()


def _parse_sse_line(line):
    line = line.strip()
    if not line or line.startswith(":") or not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "MESSAGE", "message": raw}


def _run_comic_agent(api_key, website, goal, progress_area):
    response = requests.post(
        AGENT_URL,
        headers={
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={"url": website, "goal": goal},
        stream=True,
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:1200]
        raise RuntimeError(f"TinyFish Agent returned HTTP {response.status_code}: {detail}")

    events = []
    final_event = None
    preview_url = None
    progress = []

    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            event = _parse_sse_line(raw_line)
            if event is None:
                continue
            events.append(event)
            event_type = str(event.get("type") or event.get("event") or "UPDATE").upper()
            message = event.get("purpose") or event.get("message") or event.get("status")
            progress.append(f"**{event_type}:** {message}" if message else f"**{event_type}**")

            possible_preview = (
                event.get("streaming_url") or event.get("streamingUrl")
                or event.get("preview_url") or event.get("previewUrl")
            )
            if _valid_url(possible_preview):
                preview_url = possible_preview

            progress_area.markdown("\n\n".join(progress[-16:]))
            if event_type in ("COMPLETE", "ERROR", "FAILED"):
                final_event = event
                if event_type in ("ERROR", "FAILED"):
                    break
    finally:
        response.close()

    return events, final_event, preview_url


def _find_output_links(value):
    links = []
    seen = set()

    def add_url(label, candidate):
        if not _valid_url(candidate):
            return
        lower = (label + " " + candidate).lower()
        if (
            any(word in lower for word in ("pdf", "download", "file", "cover", "image"))
            or candidate.lower().split("?")[0].endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp"))
        ) and candidate not in seen:
            seen.add(candidate)
            links.append((label or "Output file", candidate))

    def walk(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(child, str):
                    add_url(key.replace("_", " ").title(), child)
                    # Some agents return the download URL inside a text/markdown report.
                    for candidate in re.findall(r"https?://\S+", child):
                        add_url(key.replace("_", " ").title(), candidate.rstrip(".,)"))
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            for candidate in re.findall(r"https?://\S+", node):
                add_url("Output file", candidate.rstrip(".,)"))

    walk(value)
    return links


def render_comic_ebook_studio(api_key):
    st.divider()
    st.header("📚 Comic E-book Studio")
    st.caption(
        "Enter any topic to create a new illustrated comic e-book. "
        "Each request is a separate project; your other TinyFish tools remain available."
    )

    with st.expander("How this works", expanded=False):
        st.write(
            "The app searches for a suitable comic/storybook creation website, then sends "
            "your topic and publishing instructions to TinyFish Agent. The agent must "
            "create and verify a real PDF before reporting success."
        )
        st.warning(
            "TinyFish automates websites; it does not itself guarantee image generation "
            "or PDF export. Some websites require sign-in or paid credits. The app will "
            "not purchase plans or spend credits."
        )

    with st.form("comic_ebook_form"):
        topic = st.text_area(
            "What should the e-book be about?",
            value="15 motivational life lessons told through original comic stories",
            height=100,
            placeholder="Example: Adventures of young scientists discovering space",
        )
        c1, c2 = st.columns(2)
        chapters = c1.number_input("Number of chapters / stories", min_value=1, max_value=30, value=15, step=1)
        audience = c2.selectbox(
            "Target audience",
            ["Children aged 8–16", "Children aged 5–8", "Teenagers", "Young adults", "General readers", "Parents and teachers"],
        )
        c3, c4 = st.columns(2)
        language = c3.selectbox(
            "Book language",
            ["English", "Hindi", "Spanish", "French", "Other (specify below)"],
        )
        style = c4.selectbox(
            "Illustration style",
            [
                "Colourful modern graphic novel",
                "Friendly children's cartoon",
                "Anime-inspired original artwork",
                "Classic comic-book style",
                "Watercolour storybook",
                "Educational infographic comic",
            ],
        )
        author = st.text_input("Author name (optional)", placeholder="Your author / pen name")
        extra = st.text_area(
            "Additional instructions (optional)",
            placeholder="Example: Set the stories in India; use Indian names and locations.",
            height=75,
        )
        with st.expander("Advanced option"):
            website_override = st.text_input(
                "Specific comic creation website (optional)",
                placeholder="https://example.com",
            )
            st.caption("Leave blank to let TinyFish Search discover a suitable website.")
        submitted = st.form_submit_button(
            "🎨 Create my comic e-book",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not api_key or not api_key.strip():
            st.error("Add your TinyFish API key in the sidebar or Streamlit Secrets first.")
            return
        if not topic.strip():
            st.error("Enter a topic for your e-book.")
            return
        if website_override.strip() and not _valid_url(website_override.strip()):
            st.error("The website must be a complete http:// or https:// URL.")
            return

        project = {
            "topic": topic.strip(),
            "chapters": int(chapters),
            "audience": audience,
            "language": language,
            "style": style,
            "author": author.strip(),
            "extra": extra.strip(),
        }
        goal = _build_comic_goal(**project)

        try:
            with st.status("Preparing your comic e-book project…", expanded=True) as status:
                if website_override.strip():
                    selected_url = website_override.strip()
                    query = None
                    candidates = []
                    st.write("Using your selected website.")
                else:
                    st.write("Searching for a suitable comic-book creation website…")
                    query, candidates = _discover_comic_sites(api_key.strip(), topic.strip())
                    selected_url = candidates[0]["url"]
                    st.write(f"Found {len(candidates)} candidate websites.")
                    st.write(f"Selected: {candidates[0]['title'] or selected_url}")
                    st.write(selected_url)

                progress_area = st.empty()
                st.write("Starting TinyFish Agent. This may take several minutes.")
                events, final_event, preview_url = _run_comic_agent(
                    api_key.strip(), selected_url, goal, progress_area
                )
                final_type = str((final_event or {}).get("type") or "").upper()
                final_status = str((final_event or {}).get("status") or "").upper()
                result = None
                if final_event:
                    result = final_event.get("resultJson")
                    if result is None:
                        result = final_event.get("result")
                    if result is None:
                        result = final_event

                # A COMPLETE event only means the browser run ended. The agent's
                # own report may still say the requested task failed or was blocked.
                result_text = json.dumps(result, ensure_ascii=False).lower()
                blocked_terms = (
                    "blocked by authentication", "authentication requirement",
                    "unable to generate", "not created", "task status: failed",
                    "no content was created", "could not create",
                )
                task_blocked = any(term in result_text for term in blocked_terms)
                completed = (
                    final_type == "COMPLETE"
                    and final_status in ("COMPLETED", "SUCCESS", "SUCCEEDED")
                    and not task_blocked
                )
                if completed:
                    status.update(label="TinyFish run finished — verify the PDF below", state="complete", expanded=False)
                elif task_blocked:
                    status.update(label="Agent run ended, but the e-book task was blocked or failed", state="error", expanded=True)
                elif final_event:
                    status.update(label=f"TinyFish run ended: {final_status or final_type}", state="error", expanded=True)
                else:
                    status.update(label="Stream ended without a final event", state="error", expanded=True)

            record = {
                "project": project,
                "website": selected_url,
                "search_query": query,
                "candidates": candidates,
                "events": events,
                "final_event": final_event,
                "preview_url": preview_url,
                "result": result,
                "completed": completed,
            }
            st.session_state["comic_ebook_last"] = record
        except requests.exceptions.Timeout:
            st.error("The request timed out. Check the TinyFish run dashboard before starting it again.")
        except requests.exceptions.RequestException as exc:
            st.error(f"Network error: {exc}")
        except Exception as exc:
            st.error(str(exc))

    record = st.session_state.get("comic_ebook_last")
    if record:
        st.divider()
        st.subheader("E-book creation report")
        st.write("**Topic:**", record["project"]["topic"])
        st.write("**Website:**", record["website"])
        if record.get("preview_url"):
            st.link_button("Watch TinyFish browser session", record["preview_url"])

        final_event = record.get("final_event") or {}
        result = record.get("result")
        result_status = final_event.get("status") or final_event.get("type") or "No final event"
        st.metric("TinyFish run status", str(result_status))

        if result is not None:
            if isinstance(result, (dict, list)):
                st.json(result, expanded=True)
            else:
                st.text_area("Agent report", str(result), height=220)

            # Download links may be emitted in an earlier SSE event rather than resultJson.
            output_links = _find_output_links({"result": result, "events": record.get("events", [])})
            if output_links:
                st.markdown("#### Files reported by TinyFish")
                for label, url in output_links:
                    st.markdown(f"- [{label}]({url})")
            else:
                result_text = json.dumps(result, ensure_ascii=False).lower()
                if any(term in result_text for term in (
                    "blocked by authentication", "authentication requirement",
                    "no credentials", "sign in", "login", "not created",
                )):
                    st.error(
                        "The website blocked creation because sign-in is required. "
                        "No PDF or cover was created. A completed TinyFish browser run "
                        "does not mean the e-book task succeeded."
                    )
                    st.caption(
                        "Use a website where the required creation and PDF export are "
                        "available in the agent's browser session, or provide an authorized "
                        "website/account workflow. Do not share passwords in this app."
                    )
                else:
                    st.info(
                        "No verified PDF or cover download URL was found in the returned result. "
                        "Inspect the browser session and event log to determine whether the "
                        "website created the files or stopped before export."
                    )

        if record.get("search_query"):
            with st.expander("Websites considered"):
                st.caption(record["search_query"])
                for item in record.get("candidates", []):
                    st.markdown(f"- [{item['title'] or item['url']}]({item['url']})")

        with st.expander("TinyFish event log"):
            st.json(record.get("events", []), expanded=False)
