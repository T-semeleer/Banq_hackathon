import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.processing import DocumentProcessor

import streamlit as st
from pathlib import Path
from core.processing import DocumentProcessor
from config.settings import settings


def main():
    st.title("OCR Pipeline")
    uploaded = st.file_uploader("Upload PDF or image", type=[f.lstrip(".") for f in settings.supported_formats])
    fmt = st.selectbox("Output format", ["pdf", "docx", "markdown", "json", "txt"], index=0)
    if uploaded and st.button("Process"):
        suffix = "." + uploaded.name.split(".")[-1]
        tmp = settings.temp_dir / uploaded.name
        tmp.write_bytes(uploaded.getvalue())
        proc = DocumentProcessor()
        doc = proc.process(tmp, output_format=fmt)
        out_path = settings.output_dir / f"{tmp.stem}.{fmt}"
        with open(out_path, "rb") as f:
            st.download_button("Download", data=f.read(), file_name=out_path.name)

if __name__ == "__main__":
    main()