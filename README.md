# 🖼️ WallArt Wizard

**Bulk-resize images to print-ready wall art dimensions at 300 DPI — instantly.**

WallArt Wizard is a free, open-source Streamlit application that automates the tedious process of converting high-resolution images into every standard wall art print size. Upload your images, choose your sizes, and download production-ready files — all in one click.

Built for print-on-demand sellers, digital artists, and photographers who need pixel-perfect output without touching Photoshop.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| ⚡ **Parallel Processing** | Resizes to multiple sizes simultaneously using multithreaded workers (2–4× faster). |
| 🎯 **300 DPI Conversion** | Every output file is saved at 300 DPI — print-ready out of the box. |
| 📊 **Smart Quality Analysis** | Automatically scores each output size based on the upscale/downscale ratio. Resolution warnings flag images that may lose quality. |
| 📐 **5 Standard Sizes + Custom** | 2:3, ISO A1, 3:4, 4:5, 11×14 — plus an unlimited custom size option (specify inches). |
| 🎨 **Crop & Fit Modes** | Choose *Crop to Fill* (edge-to-edge) or *Fit with Background* (letterbox, no cropping). |
| 📦 **Batch ZIP Downloads** | Download one ZIP per design, or a single master ZIP containing everything. |
| 🖼️ **Multi-Format Support** | Accepts JPG, PNG, and WebP. Outputs JPEG or PNG. Handles transparency gracefully. |

---

## 🛠️ Tech Stack

- **Python 3.10+**
- **[Streamlit](https://streamlit.io/)** — Interactive web UI
- **[Pillow (PIL)](https://python-pillow.org/)** — Image processing engine
- **concurrent.futures** — Parallel worker pool (stdlib)

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or newer
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/wallart-wizard.git
cd wallart-wizard

# (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate   # macOS / Linux
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## 📖 Usage

1. **Select your settings** in the sidebar — resize mode, output sizes, format, quality.
2. **Upload one or more images** (JPG / PNG / WebP).
3. Review the **automatic quality analysis** for each image.
4. Click **🚀 Generate All Sizes** — parallel processing kicks in.
5. **Download** your print-ready files as individual or master ZIP archives.

---

## 📐 Supported Wall Art Sizes

| Key | Size | Pixels (300 DPI) | Covers |
|---|---|---|---|
| 2:3 | 24 × 36 in | 7200 × 10800 | 4×6, 6×9, 8×12, 10×15, 12×18, 16×24, 20×30, 24×36 |
| ISO A1 | 23.4 × 33.1 in | 7016 × 9933 | A5, A4, A3, A2, A1 |
| 3:4 | 18 × 24 in | 5400 × 7200 | 6×8, 9×12, 12×16, 15×20, 18×24 |
| 4:5 | 16 × 20 in | 4800 × 6000 | 4×5, 8×10, 12×15, 16×20 |
| 11×14 | 11 × 14 in | 3300 × 4200 | 11×14 |

You can also add **any custom size** by specifying width and height in inches.

---

## 🤝 Contributing

Contributions are welcome and appreciated! Here's how to get involved:

1. **Fork** the repository.
2. **Create a feature branch**: `git checkout -b feature/amazing-idea`
3. **Commit your changes**: `git commit -m "Add amazing idea"`
4. **Push to your branch**: `git push origin feature/amazing-idea`
5. **Open a Pull Request** against `main`.

### Guidelines

- Keep the code clean — follow existing style conventions.
- Add docstrings to new functions.
- Test with a variety of image sizes and formats before submitting.
- Open an issue first for large changes so we can discuss the approach.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🙏 Acknowledgements

- [Streamlit](https://streamlit.io/) for making data apps effortless.
- [Pillow](https://python-pillow.org/) for rock-solid image processing.

---

> **Made with ❤️ for the print-on-demand community.**
