import io
import pandas as pd

def inspect_file(upload):
    name = upload.name.lower()
    raw = upload.getvalue()
    if name.endswith(".csv"):
        frame = pd.read_csv(io.BytesIO(raw))
        return {"text": frame.head(150).to_string(index=False), "table": frame}
    if name.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(io.BytesIO(raw))
        return {"text": frame.head(150).to_string(index=False), "table": frame}
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(raw))
        content = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
        return {"text": content[:50000], "table": None}
    return {"text": raw.decode("utf-8", errors="replace")[:50000], "table": None}
