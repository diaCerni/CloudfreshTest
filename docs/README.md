# Project documentation

Formal documentation is generated here:

- **Enterprise_Policy_Search_Agent.docx** — Microsoft Word
- **Enterprise_Policy_Search_Agent.pdf** — PDF

To regenerate after editing content, install dependencies and run from the project root:

```bash
pip install python-docx reportlab
python docs/generate_documentation.py
```

Edit `docs/generate_documentation.py` to change wording or structure, then run the command above.
