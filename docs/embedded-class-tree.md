# Stage 4：內嵌分類樹檢視器

主頁 \`BertScript/Test_result_Vis.py\` 的「分類樹互動檢視器」現在直接使用 Dash Cytoscape。
**不需要**先啟動 Jaal 的獨立 8053 port，也沒有跨 port iframe。獨立
\`ClassesTree/Visualization/jaal/jaalViewer.py\` 仍可供原來的 Jaal CLI 場景使用，
並未移除其進階功能；內嵌檢視器目前提供子樹導覽、節點點選、手動延伸、清空與全圖模式，
不是 Jaal 原有全部搜尋／資料篩選與視覺設定的 1:1 替代品。

## 使用方式

1. 在 Stage 4 Dash 主頁找到**常駐顯示的「Classes Tree Jaal Viewer｜分類樹互動檢視器（內嵌版）」卡片**；初始只有空白畫布，
   \`elements=[]\`，不讀取 CSV、不計算全樹、不另開服務。
2. 輸入確切的英文 ClassLabel，例如 \`TW Affairs\` 或
   \`Spacetime Singularity Of Tree\`，選擇深度（預設 2）與節點上限（預設 150），
   按「繪製子樹」才按需解析 taxonomy 並回傳受限子圖。
3. 點選圖形節點可查看英文名稱與 CSV 的 CT 中文名；按「展開所選節點」才會增加其
   向外子節點（保留已顯示的節點，且受同一數量上限控制）。可隨時清空畫布。
4. 「全圖模式」預設收起、未勾選。**必須先勾確認，再按全圖按鈕**。
   全圖不做物理力導向布局且隱藏大量文字標籤，減少瀏覽器壓力；
   超過 4,000 節點或 8,000 關係時直接拒絕全圖，改用子樹。
5. 主頁不需其他網路設定，但 Python 環境必須安裝 \`dash-cytoscape\`
   （已列在根目錄 \`requirements.txt\`）。更新部署版本時需同步安裝依賴；若尚未安裝，卡片仍會顯示安裝提示，且不會讓整個主頁因缺套件而失效。

後端讀取 \`ClassesTree/data/TopicTree.csv\`、\`TopicTree_AK4.csv\` 的有向邊，
中文名稱讀取同目錄 \`ClassTable.csv\`。解析僅在點擊繪製／展開／已確認全圖後執行，
資料採檔案修改時間與大小的 bounded cache，不變更 taxonomy 原檔。
可承受的節點數仍取決於瀏覽器；全圖大小限制不保證實際 GPU/瀏覽器效能。

## 驗證

\`\`\`shell
python -m unittest -v tests.test_embedded_tree_data tests.test_embedded_tree_panel
\`\`\`

Hosted \`Stage 4 Embedded Lazy Taxonomy Graph\` 工作流程在 Python 3.11 安裝最小 Dash
與 Dash Cytoscape 套件，執行圖形資料實例、上限保護及 callback 註冊契約測試。
這些測試**不會**啟動全圖或 Jaal server，也不代表實際 Windows/手機瀏覽器互動驗收。
實機仍需驗證展開後空畫布、選根、點節點、展開、清空、未確認全圖拒絕、
與明確確認全圖時的瀏覽器回應。


## 原版 Jaal 進階區塊（保留完整視覺效果）

此區塊與前述 Dash Cytoscape 輕量分類樹**同時存在**，保留原本使用
`ClassesTree/Visualization/jaal/jaalViewer.py` + `Jaal.create()`
產生的 Search、Filter（pandas query）、Color、Size、vis.js hover/physics/
節點大小與邊權重等整套 UI；**不是**以 Cytoscape 重做 Jaal 功能。

操作：展開 Stage 4 主頁（無須獨立開 8053），在下方常駐可見的
「原版 Jaal 進階檢視器」輸入英文 `QueryRoot`，點「載入原版 Jaal」。
預設 `TW Affairs`，目前完整子樹約 77 節點。若子樹超過 250 節點，
先勾「大型子樹」確認後才能繪製。硬限制 3,000 節點或 5,000 邊，
超過拒絕並請使用更小的根節點。

**啟動行為**：主頁初始只顯示控制面板，沒有 iframe，沒有
`Jaal.create()`、沒有載入 Jaal 的節點資料。使用者明確按下按鈕後
才建立同源 iframe（路徑 `/jaal-original/<hash>/`），真正首個
iframe HTTP 請求才建立與緩存原版 Jaal Dash app。底層透過
Werkzeug DispatcherMiddleware 轉送到同一個 Flask/WSGI port，
不啟動第二個服務。每個 Stage 4 worker 同時最多保留三個不同
QueryRoot 的原版 Jaal 實例，避免無上限耗用記憶體；改變根類別重新
載入，回呼與視覺設定會重設。單機多 worker 各自有實例與狀態；
以主站 process-local 行為為準，不宣稱跨 worker session 同步。

如尚未安裝，先於主站 Python 環境執行
`python -m pip install jaal`，並確認相容的 `dash`、`visdcc`、
`dash-bootstrap-components`；更新後重新啟動主站，必要時瀏覽器
`Ctrl+F5`。直接開啟未由主頁啟用的子路徑會回傳 404。
這個 Jaal 區塊包含原本 UI 的篩選、顏色與大小設定，輕量區塊維持
獨立，兩者不會互相覆蓋。

真實 Windows 主頁／Jaal 全量互動仍需實機驗收（尤其版本相容性、
跨欄顯示與瀏覽器效能）；CI 使用小型原版 Jaal app 驗證同 port
資源及 callback 路徑，不等同 2,648 節點實際順暢繪圖。
