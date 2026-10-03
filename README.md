# PDF Localization Tool

將含中文文字層的 PDF 轉換為台灣繁體中文，並盡量保留原始版面。

## 安裝

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 設定來源 PDF、輸出位置及中文字型後執行：

```bash
python pdf_localize_tw.py
```

預設不覆寫既有輸出；確定要覆寫時才設定 `PDF_OVERWRITE=true`。

## 隱私

原始文件、輸出 PDF、預覽圖片及轉換報告可能含客戶或公司資料，已由 `.gitignore` 排除，請勿提交至公開 repository。
