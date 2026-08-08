
   *(Done.)*
</think>

# Code Fragment

A curated collection of AI agent skills, automation scripts, and utilities designed for complex document workflows and modern web development. This repository provides structured guidelines, executable scripts, and configuration examples for generating, editing, and manipulating Office documents (DOCX, PPTX), filling PDF forms, and automating browser-based tasks, alongside a production-ready React + Vite starter project.

## 📦 Installation

**Prerequisites:**
- Node.js (v18+)
- Python 3.9+
- `libreoffice` (for `.doc`/`.docx` conversion & PDF export)
- `poppler-utils` (provides `pdftoppm` for image extraction)

### Frontend Application (`html/jietiao`)
The React project uses Vite 6, React 19, Tailwind CSS v4, Express, and Better-SQLite3.

```bash
cd html/jietiao
npm install
```

### Document Processing Scripts (`articles/copaw-skills/`)
Scripts rely on standard Python libraries and `defusedxml`. For DOCX creation, install the `docx` package globally:

```bash
npm install -g docx
```

Additional Python dependencies (e.g., `python-docx`, `pdf2image`, `markitdown`) should be installed according to the specific `SKILL.md` instructions in each directory.

## 🚀 Usage

### 🌐 React Application
Start the development server:
```bash
npm run dev
```
Build for production:
```bash
npm run build
npm run preview
```
Run linter & type checks:
```bash
npm run lint
```

### 📄 AI Agent & Document Workflows
This repository is structured around executable "skills" that guide AI agents or developers through step-by-step document manipulation.

**DOCX Generation & Editing**
- Create professional Word documents using `docx-js` or Python scripts.
- Unpack, edit XML, and repack documents:
  ```bash
  python scripts/office/unpack.py input.docx unpacked/
  # [Edit unpacked/word/document.xml]
  python scripts/office/pack.py unpacked/ output.docx --original input.docx
  ```

**PDF Form Filling**
- Extract form structure, validate coordinates, and fill annotations:
  ```bash
  python scripts/extract_form_structure.py input.pdf form_structure.json
  python scripts/check_bounding_boxes.py fields.json
  python scripts/fill_pdf_form_with_annotations.py input.pdf fields.json output.pdf
  ```

**PPTX Editing**
- Modify slides using template-based workflows:
  ```bash
  python scripts/office/unpack.py template.pptx unpacked/
  # [Edit unpacked/ppt/slides/slide{N}.xml]
  python scripts/clean.py unpacked/
  python scripts/office/pack.py unpacked/ output.pptx --original template.pptx
  ```

## 📁 Repository Structure

```
code-fragment/
├── html/
│   └── jietiao/            # React + Vite + Tailwind CSS example
└── articles/
    └── copaw-skills/       # AI Agent skill definitions & automation scripts
        ├── docx/           # Word document generation, editing, and validation
        ├── pdf/            # PDF form extraction, bounding-box validation, and filling
        ├── pptx/           # PowerPoint template manipulation and slide editing
        ├── file_reader/    # Guidelines for reading/summarizing text-based files
        └── news/           # Browser automation workflows for news aggregation
```

## 📖 Documentation & Guidelines

Each skill directory contains a `SKILL.md` or detailed `.md` guide outlining:
- **Runtime Dependencies**: Required system tools, Python packages, or browser extensions.
- **Step-by-Step Workflows**: From unpacking and validation to final repacking and QA.
- **Critical Rules**: Best practices for XML formatting, tracked changes, smart quotes, and table/layout consistency.
- **Validation & Auto-Repair**: Built-in Python validators that check schema compliance and fix common XML issues.

Refer to the individual `SKILL.md` files for complete code references, formatting rules, and troubleshooting tips.
