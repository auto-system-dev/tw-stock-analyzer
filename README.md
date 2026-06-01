# TW Stock Analyzer

台灣股票技術分析與價格趨勢預測工具。透過 Yahoo Finance 擷取台股歷史資料，計算技術指標，並以機器學習模型預測短期價格走向。

## 功能

- **資料擷取**：支援台股代號（如 `2330` 自動轉為 `2330.TW`）
- **技術指標**：SMA(5/20/60)、RSI、MACD、布林通道、波動率
- **價格預測**：Random Forest 預測 N 日後收盤價變化
- **訊號綜合**：均線、RSI、MACD、布林規則與模型輸出整合判斷
- **網頁儀表板**：Streamlit 互動圖表與預測結果
- **消息面**：新聞、公告、社群（Google News RSS）
- **題材偵測**：AI、法說、訂單、股利等關鍵字
- **基本面**：PER、PBR、EPS、月營收 YoY（Yahoo + FinMind）
- **籌碼**：外資 / 投信 / 自營近 N 日淨買超（FinMind）

## 安裝

```bash
cd tw-stock-analyzer
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pip install -e .
```

### FinMind API（建議，籌碼與台股新聞）

1. 至 [FinMind](https://finmindtrade.com/) 註冊並取得 API Token  
2. 複製 `.env.example` 為 `.env`，填入：

```bash
FINMIND_API_TOKEN=你的_token
```

Windows PowerShell 單次設定：

```powershell
$env:FINMIND_API_TOKEN = "你的_token"
```

籌碼、月營收、台股新聞等透過 **FinMind REST API** 取得（已內建，無需額外安裝 `finmind` 套件）。未設定 Token 時每小時請求次數較少，建議註冊取得 Token。

## 使用方式

```bash
# 分析台積電（2330），預設預測 5 日
tw-stock analyze 2330

# 指定資料期間與預測天數
tw-stock analyze 2317 --period 1y --horizon 10
```

也可直接執行模組：

```bash
python -m tw_stock_analyzer.cli analyze 2330
```

### 網頁儀表板

```bash
# 方式一：指令
tw-stock-dashboard

# 方式二：Streamlit 直接啟動
streamlit run tw_stock_analyzer/dashboard/app.py
```

瀏覽器開啟 `http://localhost:8501`，輸入股票代號後按「開始分析」，於 **消息面** 分頁查看基本面、籌碼、新聞與題材。

### 回測（比較策略）

```bash
tw-stock backtest 2330 --strategy both
tw-stock backtest 2330 --strategy rsi --hold 5
```

儀表板側欄「執行回測」或「回測」分頁可並排比較綜合方向與 RSI 超賣策略。

## 部署到 Railway

本專案以 **Streamlit 儀表板** 作為網頁服務，已包含 `Dockerfile`、`railway.toml`、`start.sh`。

### 前置準備

1. [Railway](https://railway.com/) 帳號
2. 將專案推送到 **GitHub**（GitLab 亦可）
3. （建議）FinMind API Token

### 部署步驟

1. 登入 Railway → **New Project** → **Deploy from GitHub repo**
2. 選擇 `tw-stock-analyzer` 儲存庫
3. Railway 會自動偵測 `Dockerfile` 並開始建置
4. 進入服務 → **Variables**，新增：

| 變數名稱 | 說明 |
|----------|------|
| `FINMIND_API_TOKEN` | FinMind Token（選填，建議設定） |

5. **Settings** → **Networking** → **Generate Domain**，取得公開網址（例如 `https://xxx.up.railway.app`）
6. 開啟網址即可使用儀表板

### 注意事項

- **不需**手動設定 `PORT`，Railway 會自動注入；`start.sh` 已綁定 `0.0.0.0`
- 免費方案記憶體有限，首次「開始分析」可能較慢（需下載股價並訓練模型）
- 若建置失敗，確認 repo 根目錄含 `Dockerfile`、`requirements.txt`、`tw_stock_analyzer/`（勿只用 GitHub 網頁上傳少數檔案）
- 建置錯誤若出現在 `apt-get`：請拉取最新版 `Dockerfile`（已改為不需安裝系統套件）
- 本工具僅供研究，公開部署請自行評估風險與免責聲明

### 本機用 Docker 測試（選用）

```bash
docker build -t tw-stock-analyzer .
docker run -p 8501:8501 -e FINMIND_API_TOKEN=你的token tw-stock-analyzer
```

瀏覽器開啟 http://localhost:8501

## 專案結構

```
tw-stock-analyzer/
├── tw_stock_analyzer/
│   ├── data/          # 股價、基本面、籌碼、新聞、題材
│   ├── indicators/    # 技術指標
│   ├── predictor/     # ML 預測模型
│   ├── analyzer/      # 分析引擎
│   ├── backtest/      # 策略回測與績效比較
│   ├── dashboard/     # Streamlit 網頁儀表板
│   └── cli.py         # 命令列介面
├── requirements.txt
└── pyproject.toml
```

## 後續規劃

- [x] 回測模組（驗證策略勝率）
- [x] Streamlit 網頁儀表板
- [ ] 上櫃股票（.TWO）代號自動判別
- [x] 法人籌碼、營收等基本面資料
- [ ] 多檔股票批次掃描

## 免責聲明

本工具輸出僅供學習與研究，不構成任何投資建議。股市有風險，投資請謹慎評估。
