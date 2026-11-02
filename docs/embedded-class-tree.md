# Stage 4：內嵌分類樹檢視器

## Jaal 獨立套件來源（2026-11-02）

原本的圖形核心、四種網狀／階層佈局與瀏覽器 JS，現由
[jaal-topology-viewer](https://github.com/hun186/jaal-topology-viewer)
獨立 Repository 維護。 `text-category-profiler` 在 `requirements.txt`
使用 **固定 Git Commit** 的 `jaal-topology-viewer` 相依套件，
不再從 `packages/jaal-topology/` 載入或附帶核心程式碼。

主站內嵌的 `BertScript.jaal_original_mount` 仍保留特殊 UI：
根節點搜尋、需求時才載入的同埠 WSGI router、原 Jaal
Search/Filter/Color/Size、ClassTable 的 CT 中文回退、左側面板
收合及 iframe 自動高度。原有 `--viewer-only` 和 port 8059
操作方式**沒有改變**。JS 由已安裝套件的 `ASSETS_DIR`
提供，版型 `layout_options` 改用標準 Python `import`。

更新程式碼與套件後若仍在 Windows 執行舊 Python 行程，請停止
現有 8059 服務、安裝新的 `requirements.txt`（需具備 Git
及可用的套件來源；離線則需預先提供對應 Wheel），再重新啟動。
Hosted 的確保範圍為獨立套件 CI、原版 Jaal WSGI、Node JS 與
Python 回歸；**Windows 實際瀏覽器像素與操作驗收仍待確認**。


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


## 唯讀 GUI 直接啟動（無 WorkPool、免重新分類）

如果只要測試 Jaal 分類樹互動（包括網狀／階層樹狀切換），
不需要從 `TCFMain.py` 或完整 Stage 4 流程開始。
在專案根目錄的 Windows CMD／Anaconda Prompt 執行：

```bat
python BertScript\Test_result_Vis.py --viewer-only -p 8059
```

或在 Windows 直接執行專案根目錄的
`run-jaal-viewer-only.bat`（同樣是本機 port 8059）。
開啟 `http://127.0.0.1:8059/`，輸入根類別後按「載入 Jaal」。

這個模式在載入 Stage 4 其餘大型依賴及資料集掃描前就分流，
**只**建立原本的同 port Jaal card；只綁定
`127.0.0.1`、不使用公開網路界面，不呼叫
`datasetDirOutputDirPickers`、不啟動模型／分類分析、
不修改 `WorkPool`、不執行資料夾重新命名或 Stage 4 的
`_rdy_for_TestResultVis → _is_running_TestResultVis → _rdy_for_Spike`
交接。若資料集已在 `_rdy_for_Spike`，**不要把它手動改名回去**。
停止 GUI（Ctrl+C）不會推進 WorkPool 階段。

**範圍限制：** `--viewer-only` 是獨立 Jaal 分類關係檢視，不是
「重新載入完整 Stage 4 分析結果」。原有 DataTable、統計圖表與
模型結果仍只能經正式 Stage 4 資料流程取得；
此模式仍需安裝相容的 Dash／Jaal／visdcc，
按「載入 Jaal」才會依 TopicTree 解析有界子樹。
如果 8059 已被占用，可用 `-p 8060` 更換本地 port。
它與原來的 Jaal-only `createMode` 都不應寫入正式 taxonomy。

Hosted Jaal CI 包含 `tests.test_jaal_viewer_only`：
驗證實際 `Test_result_Vis.py --viewer-only --help` 在無資料／模型的
空工作目錄可用、服務固定 loopback、無 WorkPool rename、
啟動主頁沒有預載 iframe，並保留原有 Jaal Search／Filter／Color／Size。

## Jaal 進階檢視器（保留完整視覺效果）

此區塊與前述 Dash Cytoscape 輕量分類樹**同時存在**，保留原本使用
`ClassesTree/Visualization/jaal/jaalViewer.py` + `Jaal.create()`
產生的 Search、Filter（pandas query）、Color、Size、vis.js hover/physics/
節點大小與邊權重等整套 UI；**不是**以 Cytoscape 重做 Jaal 功能。

操作：展開 Stage 4 主頁（無須獨立開 8053），在下方常駐可見的
「Jaal 進階檢視器」輸入英文 `QueryRoot`，點「載入 Jaal」。
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

### 網狀／階層樹狀顯示模式

已載入的 Jaal 檢視器，在分類圖上方（左側設定收合按鈕旁）
新增 **顯示模式：網狀／階層樹狀**。預設 **網狀**，完全使用 Jaal
原本的 vis.js options（含 hover、箭頭、physics 設定）。切到
**階層樹狀**時，用相同節點與關係啟用 vis.js
`layout.hierarchical.enabled`（`direction=UD`、`sortMethod=directed`）、
停用物理力，並以垂直 cubicBezier 曲線顯示關係；
切回網狀時，因 visdcc 的 `setOptions` 會合併既有選項而非取代，會明確設 `hierarchical.enabled=false`、還原樹狀 cubicBezier 為原始設定（未指定則 dynamic 預設），並在階層引擎完成內部狀態還原後，透過短暫的一次性計時回呼**第二次**設定 physics.enabled 與完整原始 edge smoothing，以避免被 vis.js 舊布局備份覆寫。計時器其餘時間停用，快速切回階層時不會誤啟動 physics；其餘原始 Jaal options 保留。

### 階層模式長類別名稱防重疊（同埠 Jaal）

階層圖中同一層含大量英文 ClassLabel 時，原先 175px 的節點間距
不足以容納完整單行文字。內嵌 Jaal 的 **階層模式**現在對節點
標籤設定 vis-network `nodes.widthConstraint.maximum=145`，使有空白
的英文長名稱依寬度自動換行；同時將水平同層間距改為 245、
不同樹間距 310、垂直層距 205，並保留導向邊及既有的
Search／Filter／Color／Size。沒有變更 ClassLabel、邊、選取狀態
或完整原始圖形資料。顯示過密時仍可放大／拖曳，或從更細的根類別載入；
**不宣稱 77 個節點全部在單一螢幕寬度下都能同時清楚閱讀**。

切回**網狀**時，由於 visdcc／vis-network 對 options 採合併更新，
會明確還原原本的 `nodes.widthConstraint`（未設定則 `false`），
並連同原本的 physics 與 edge smoothing 一併透過既有的
一次性 timer 恢復，避免網狀模式仍受階層標籤換行限制。
這只修改同 port 內嵌版；獨立的 Jaal CLI 原樣保留。
Hosted 回歸測試包含 options、WSGI callback 與反覆切換，
真正 Windows 瀏覽器視覺間距仍需實機確認。

切換僅更新既有 `visdcc.Network(id="graph").options`，不更動
`graph.data`、Search／Filter／Color／Size 已選設定、左側面板收合，
也不重新建立 Jaal Dash app 或開新 port。載入另一個根類別時會
恢復網狀預設。TopicTree 是有向圖，可能有多父節點、跨層關係或
環狀關係；階層模式是**視覺布局選擇**，不保證變成嚴格單根樹，
也不修改分類結構或隱藏交叉連線。

這個切換僅加在 Stage 4 **同 port 內嵌版**，不改動獨立
`jaalViewer.py` 的 CLI 版型。Hosted 原版 Jaal WSGI 測試會驗證
實際 Dash layout 的模式選項、graph.options HTTP callback、
階層模式參數及切回網狀後 options 完整一致；Windows 瀏覽器
實際渲染、切換時的視角與大型圖形效能仍需實機確認。

### 原版 Jaal 不必要的水平／垂直雙捲軸

原版 Jaal 直接將 Logo 與 Search／Filter／Color／Size＋網路圖兩個
Bootstrap `Row` 放在 `html.Div` 下，並非放在具有 gutter
補償的 `container` 裡。Bootstrap `.row` 的左右負邊距可能使
iframe 內容比可用寬度多出約數個至十數像素，出現水平捲軸；
捲軸再占掉部分高度，也可能誘發垂直捲軸。

同 port **內嵌版**只對原版 Jaal 這兩個最外層 `Row` 增加
Bootstrap `g-0`：將 gutter 歸零並抵消負邊距造成的溢出。
內層 Filter／Color／Size 排版、已有的側欄收合、實際內容高度
自動計算、600px vis.js 畫布與獨立 8053 Jaal 均不變。
**沒有**把 iframe 或頁面設成 `overflow:hidden`，因此若縮窄
瀏覽器或展開很長的內容，真正必要的捲動仍保留。
Hosted 原版 Jaal 的 WSGI layout 測試確認兩個外層 `Row` 使用
`g-0`、內層控制不被改寫、Bootstrap CSS 有對應樣式；
Chrome／Windows 實機的捲軸消失情況仍需使用者確認。

### 原版 Jaal 左側面板固定靠上對齊

原版 Jaal 的左側 Search／Filter／Color／Size 面板原本使用
`align-items: center` 在圖形欄旁**垂直置中**；當 Filter 或 Color
收合、左側內容變矮時，卡片上方就出現隨內容高度改變的大塊空白。
同埠內嵌版現在將**初始**左側欄位改為
`align-items: flex-start`，並在「收合／展開左側設定」回呼中
同樣維持靠上。設定面板高度仍隨 Filter／Color 開合自然增減，
不更改 Search／Filter／Color／Size 的 callback 或控件狀態。
右側 vis.js 圖形內容、圖形縮放與原版獨立 8053 Jaal 不變。
這是純排版修正；真正 Windows 瀏覽器的視覺驗收仍需確認。

### 原版 Jaal 左側設定面板收合／展開

在已載入的原版 Jaal 子視窗中，圖形區上方有常駐可見的
**「◀ 收合左側設定」**按鈕。按下後 Search／Filter／Color／Size
左側設定區隱藏，右側分類圖從 Bootstrap 9 欄（75%）擴展成
12 欄（100%）；按**「▶ 展開左側設定」**可恢復原本 3／9 欄。
按鈕放在圖形欄內，所以隱藏設定區後仍可操作；不必重新選擇
根類別或重新載入 Jaal。鍵盤可聚焦並按 Enter／Space 操作。

這個功能只套在 **same-port 內嵌版**：保留原版 Jaal 的圖形
`graph.data`、原有所有 Search／Filter／Color／Size 回呼與選擇，
不重新建立 visdcc.Network、不改物理力選項、也不呼叫 `fit()`
重設使用者視角。欄寬變更後透過瀏覽器 `resize` 通知
vis.js 重算容器尺寸。獨立 8053 CLI 視窗仍維持原樣。
每次重新載入整個 iframe 時，設定區會回到預設展開狀態。

Hosted 測試會在原版 Jaal 的子路徑 HTTP 介面實測收合／展開
回傳的 12 欄與 9 欄、原圖未重建及所有原版 callbacks 仍存在。
實際 Windows 瀏覽器中的 network canvas resize 與功能互動需使用者
確認，不能把 Hosted HTTP 測試視為視覺驗收完成。

### 原版 Jaal 下方大面積空白：iframe 自動適應高度

先前 Stage 4 的原版 Jaal iframe 固定 `height: 1100px`，但 Jaal
網路畫布本身 `vis_opts.height = 600px`。這會在圖形／控制面板的
實際內容結束後留下多餘空白，收合左側設定後尤為明顯。

嵌入版現在提供 `800px` 的初始／無 JavaScript 備援高度，待
Dash 在 iframe 中渲染原版 Jaal 後，才由同源的
`BertScript/assets/15.jaal_embedded_autoheight.js` 以
`ResizeObserver` 量測 `jaal-original-content` 元素的
實際底部，對父 iframe 設定適當高度（最低 640、最高 1,600px，
附 16px 內距）。收合／展開設定面板或瀏覽器改變寬度後會重算。
由於是同源同 port，不需要額外通訊服務或跨站訊息。
不會重建網路、調整 `graph.data`、變更原版 600px 視圖高度、
強制 `fit()` 或重設縮放位置；超出高度安全上限的長表單仍可在
iframe 內捲動。直接開獨立 8053 Jaal 及主頁未按「載入」前的
行為均不變。

Hosted CI 除原有 Jaal WSGI／callback 測試外，新增無瀏覽器
Node 隔離測試，驗證初始渲染、Dash 延後 hydration、
收合／展開後高度更新、上下界及非 Jaal 頁面不被影響。
Windows 實際瀏覽器的畫布空白／重繪情況仍須實機驗收：
若圖形本身的 600px canvas 內部節點集中在上半部，
此修正不會把原圖 zoom 改掉，仍可能需要另外分析物理布局。

### 原版 Jaal 嵌入版排版／Logo 修復

原版 Jaal 的 `html.Img(width="80px")` 使用不合法的 HTML 圖片寬度字串，
某些瀏覽器會忽略而顯示原圖尺寸；同時 Jaal 原本從外部 CDN 引入
Bootstrap 版面樣式，一旦連線被擋，左側 Search／Filter／Color／Size
與右側 visdcc graph 的 `dbc.Row`／`dbc.Col` 25%／75% 格線會失效。
同 port 嵌入版現在只針對原版內嵌 Logo 正規化為數字 `width=80`
及 80px CSS，並從現有 `BertScript/assets/bootstrap@5.3.1/bootstrap.min.css`
提供同源樣式；不修改原版 Jaal 的獨立 8053 CLI、原先網路繪製選項、
篩選 callback 或圖形資料。這也是為離線／封閉網路場景保留的本地資源。

Hosted `Stage 4 Original Jaal Same-Port Compatibility` 檢查會實際 GET
同源 Bootstrap CSS、驗證子路徑正確，並解析原版 Dash layout JSON
檢查 Logo 寬度、視覺化 network 及各種 callback 是否保留。它不是
Windows 真實瀏覽器的視覺截圖驗收；若更新後畫面仍被放大，請提供
該 iframe 的 DevTools Network（CSS 200/404）與瀏覽器縮放比例以查明。

真實 Windows 主頁／Jaal 全量互動仍需實機驗收（尤其版本相容性、
跨欄顯示與瀏覽器效能）；CI 使用小型原版 Jaal app 驗證同 port
資源及 callback 路徑，不等同 2,648 節點實際順暢繪圖。
\n\n### 階層圖標籤不換行的實機修正\n\n先前 PR #187 的 `nodes.widthConstraint.maximum=145` 是 vis-network\n希望在標籤實際寬度超過 145px 且遇到詞間空白時換行的設定，\n**不是 145 個字、也不是 Jaal 的必然換行規則**。Windows 實測的\nvisdcc／dot 節點未產生任何可見換行，因此僅靠 options 並未修好。\n\n同埠內嵌版 Jaal `createMode=True` 現在明確以\n`ClassesTree/Visualization/jaal/label_format.py` 格式化**顯示用**\n`node_df.label`：最長每行約 17 個字元、最多三行，\n儘量在英文詞／連字號處斷行；超長者在第三行末尾顯示省略符號。\n完整的 `ClassLabel` 仍保留於 `node_df.id` 及滑鼠提示\n`node_df.title`，既有 TopicTree、邊、欄位與原始搜尋／篩選\ncallbacks 不更動。新方法直接透過 Jaal 官方支援的 label/title 欄位\n輸出換行文字，並由 Hosted 真實 Jaal Dash layout HTTP 測試驗證\n資料包含換行，而非只測 options JSON。\n\n**範圍限制：**由於原版 Jaal 在同一個 graph.data 中共用\n網狀與階層模式的節點標籤，同埠檢視器的**兩種模式**都會顯示此\n多行／縮短文字（畫面文字改變，但節點 ID、tooltip 與原版控制保留）；\n獨立 8053 CLI 不受影響。這是為了避免攔截或複寫原版\nSearch／Filter／Color／Size callbacks。若要依模式獨立切換原名／短名，\n需要後續額外確認回呼相容性，不能宣稱此版本已做到。\n真實 Windows 瀏覽器依然需要用戶確認畫面，Hosted Jaal 測試不等於\n任何螢幕寬度下「所有 77 個節點都不重疊」的保證。\n

**搜尋相容性補充：**上游 Jaal 的 `_callback_search_graph` 預設對
`node.label` 搜尋，不能單靠保留 `id/title` 宣稱全文仍可搜尋。
內嵌版在 `Jaal.create()` 註冊 callbacks 之前，將此一 instance
的搜尋方法改為比對原始完整 `node.id`（沿用原本 substring、不分
大小寫與 `hidden` 更新契約），因此橫跨換行的完整名稱及第三行後
被省略的文字仍可搜尋；不改 Filter／Color／Size 回呼。
已加入真正使用 WSGI 發送 Search callback 的回歸測試。


### 8059 顯示舊標籤的診斷：執行中 Python 與 Git checkout 版本不同

`git pull` / GitHub Desktop 更新的是磁碟檔案，已執行的
`python BertScript/Test_result_Vis.py --viewer-only -p 8059` 服務不會
自動重新 import。`OriginalJaalRouter._apps` 也在 Python 記憶體中
以根類別快取已建立的原版 Jaal Dash App。瀏覽器 Ctrl+F5、重新按
「載入 Jaal」都不能讓舊 Python 程序換成新版本。

內嵌 Jaal 圖形列新增**「標籤版本：multiline-labels-v2」**標記，
此字串由**當前正在執行的 Python 模組**產生，而不是直接讀 Git HEAD。
如果 Git Desktop 已顯示含有此功能的提交，但畫面沒有標記，
請先在終端機以 Ctrl+C 結束舊服務，再於專案根目錄執行
`python BertScript/Test_result_Vis.py --viewer-only -p 8059`，
確認沒有其他程序佔用 8059，然後瀏覽器 Ctrl+F5 並按「載入 Jaal」。
標記出現僅證明 GUI 已載入新版 Python 程序，**不是**所有標籤
均不重疊的 Windows 視覺驗收。

新的 `prepare_embedded_jaal_nodes` 是正式 `createMode` 的標籤轉換
共用入口，同時由真實 Jaal/Dash WSGI HTTP 測試的節點資料建立流程
呼叫。避免測試自行加工 `label` 卻遺漏正式入口的回歸風險。


### v3：階層圖改用容納多行文字的框狀節點

2026-11-02 使用者已證明 Windows 8059 執行 `multiline-labels-v2`
且 77 節點／81 邊仍有同層標籤嚴重覆蓋；**不是程式未更新**。
Jaal `parse_dataframe` 會為每個節點設定 `shape: dot`；這個
節點屬性優先於 vis-network 全域 `nodes.shape`。圓點下方的
標籤不計入節點自身排版尺寸，單純插入換行不足以防止互疊。

內嵌版 Jaal 現在**僅移除 shape: dot 這個顯示用覆寫**，讓
vis-network 可隨模式切換：原始網狀模式使用 dot，階層模式使用
box、最大標籤寬度 178、內距 12、加大同層與層距；因此階層
引擎會把文字放在保留空間的節點框內，減少框外標籤重疊。
搜尋仍依完整 id，完整 title 與所有 filter/color/size/edge
資料不更動；獨立 Jaal CLI 不受影響。修正版版號為
`hierarchical-box-labels-v3`，Windows 使用者需重啟 8059
並驗證是否能辨讀，不能把 Hosted options／HTTP 資料測試
宣稱為實際瀏覽器像素驗收。


### v4：修正 visdcc 瀏覽器最終畫面仍是單行標籤

Windows 8059 實機已確認載入 `hierarchical-box-labels-v3`，框狀
節點有效，但文字仍是一行。上一版回歸測試只驗證 Dash
`_dash-layout` 的 node.label 換行字串；它**沒有**驗證
`visdcc.Network` 於瀏覽器端維護的 vis.DataSet 最終標籤。

v4 保留原 Jaal 七項進階 callbacks、節點 ID、完整 tooltip／來源 CSV
與框狀節點版面，但在子 Dash 掛載時額外註冊一個互不干擾的
`graph.run` clientside callback：在模式或 `graph.data` 改變時，
以靜態 JavaScript 使用 visdcc React component 的
`this.nn.get()/update()`，直接將**實際畫在 canvas 上的 label**
投影為階層模式最多 3 行／每行最多 17 字元；切回網狀模式恢復
完整單行名稱。節點 `id/title/size/color` 與連線不變，不會把
使用者提供的名稱插進 eval 程式碼。

`tests/jaal_visible_labels.test.cjs` 以模擬 vis.DataSet 執行
同一段 JS，斷言真正經過 DataSet.update 後含有換行，並回歸驗證
網狀恢復與無程式碼注入；真實 Jaal WSGI 測試檢查
`graph.run` 的 Dash callback 及 JS 資源確實同源供應。
這比只檢查 Python JSON 更接近渲染端，但 Hosted 沒有進行
Windows Chrome 像素驗收，不應誤稱實機已解決。
顯示版本：`canvas-multiline-v4`。


### 類別結構收攏檢視（MVP v1）

使用者可選四種顯示模式：網狀／階層各自有「全展開」與
「收攏」。前兩種既有全展開模式維持；收攏模式只隱藏
**當前已載入 Jaal 子圖中的原始節點**，不建立新節點、
不修改分類 CSV，也不將 DAG 多父節點複製成多份。

初始顯示無父節點的分支根與直接子節點；點擊有下層的節點
展開下一層，再點同一節點收合。未展開的節點只顯示
**類別名稱／下一行唯一子孫數字**；沒有子孫者不顯示 `0`。
整張圖上方一次說明數字意義，不在每個節點重複說明文字。

唯一子孫＝沿目前 Jaal 有向父子邊可到達的不同節點數，
不計節點自己、不計邊數、不因多父路徑重複計數。
既有 Jaal 匯入邏輯的兩欄 TopicTree 邊即為父子關係；
若有未來新增非階層類型，應先將關係類型保存於圖資料
才能安全分辨，不能把非階層關係擅自視為子孫。
環狀資料使用 visited-set 截止，避免無限遍歷；沒有入度為零
的孤立環由字典序首位節點作穩定顯示起點。

此版由 visdcc 原本的 `graph.run` 和 `this.net.on('click')`
實作，只在瀏覽器內更新 `vis.DataSet` 的顯示標籤、`hidden`
與可見邊；原始 Jaal Search／Filter／Color／Size callback
仍是 graph.data 的唯一寫入者。完整模式切回時依該來源
重設可見性，避免把收攏誤認作永久篩選。
目前**不包含依縮放等級自動收攏／展開**；可縮放與拖曳檢視，
逐層展開先用單擊確保含多父關係的行為一致。
測試驗證 DataSet update 實際改變、DAG 去重、環狀終止、
兩種收攏／全展開互切、完整名稱 tooltip 與搜尋可見性還原。
Windows Chrome 的實際點擊與畫面仍需實機 acceptance。


**收攏與原版 Search 互動**：當 Search 顯示深層匹配節點時，
收攏檢視暫時顯示匹配節點及所有祖先路徑，避免匹配結果被收攏層遮蔽；
清空搜尋後恢復原本的逐層收攏與點擊操作。
仍收攏的分支不顯示其對外子邊，即使同一子孫已從其他父分支可見；
但可見子孫本身僅維持一個原始節點。


### 階層收攏重新排版：僅以目前可見子圖安排節點

Windows 實機顯示，既有 `hierarchical-collapsed` 雖隱藏大量子孫，
vis-network 階層 LayoutEngine 仍以整份含隱藏節點的 DataSet 佈局，
導致收攏後的根與少量子節點仍橫向分布很遠。

這個修正只在**階層收攏**將不可見節點與邊從瀏覽器內部
`this.nn`、`this.ee` 暫時移除，讓階層演算法的工作圖就是可見子圖。
按節點展開、收回後按需從原始 Dash `graph.data` 恢復或移除，
並透過 `net.fit({nodes: visibleIds, animation: false})` 對準目前圖形。
切回全展開或網狀收攏時，全部來源節點與連線完整復原，
搜尋、原始完整 tooltip、子孫去重數及其他 Jaal 控制不改。
網狀收攏依然採原本的物理佈局，不在此批修改。

Hosted Node 回歸驗證 DataSet 真的只含可見節點、逐層展開重佈局、
從階層收攏切往網狀／全展開能重建所有 node/edge IDs，
以及深層搜尋顯示路徑和回到原始篩選狀態。
實際 Windows Chrome 的視覺佈局仍需重新啟動 8059 後驗證。


### 跨電腦部署：Jaal 載入失敗只顯示 AttributeError 的診斷

如果主頁先顯示「已要求載入：TW Affairs；77 個節點／81 條關係」，
但下方 iframe 卻顯示「原版 Jaal 載入失敗：AttributeError」，表示
已完成計算子樹大小，**建構 Jaal Dash 子程式**的階段失敗；
`AttributeError` 不足以證明是哪一個屬性缺失。

這個修正讓 `OriginalJaalRouter.__call__` 把完整 Python
exception traceback 記到**正在執行 8059 的終端機**，HTTP
網頁仍只顯示簡潔、安全的錯誤類型，不回傳本機路徑、環境設定或堆疊。
另新增唯讀本機診斷入口（同一台電腦、同一個 Python 環境）：

```bat
python -m BertScript.jaal_runtime_diagnostics --root "TW Affairs"
```

或雙擊專案根目錄 `run-jaal-diagnose.bat`（請確認其使用的是跟
啟動 viewer 相同的 Python 解譯器）。診斷列出 Python 執行檔、
`jaal/visdcc/dash/dash-bootstrap-components/pandas/werkzeug/flask`
安裝版本，再以相同 `JaalViewMain(createMode=True)` 與
`prefix_original_jaal` 路徑建構圖形（**不開監聽埠、
不執行 ML 模型、不更動 WorkPool 或 taxonomy CSV**）。
成功顯示 `JAAL_DIAGNOSE_PASS`，失敗以 exit code 2 及完整
traceback 顯示 `JAAL_DIAGNOSE_FAILED`。診斷輸出只顯示於
本機終端機，分享前請檢查／遮蔽個人檔案路徑等資訊。

切勿僅憑 `AttributeError` 就重裝或任意升降版所有套件；
先比較可運作電腦與失敗電腦的實際 traceback、Python executable
及套件版本，再進行**有依據的**最小修正。Hosted 真 Jaal
WSGI CI 不能取代異機 Python 安裝版本相容驗收。


### 已確認：Dash 3／4 與過舊 visdcc 在跨電腦部署時不相容

2026-11-02 另一臺 Windows 的 traceback 顯示：
`visdcc/__init__.py` 呼叫 `dash.development.component_loader.load_components`，
最後拋 `AttributeError: module 'dash.development' has no attribute 'component_loader'`。
**Dash 3 起移除了 component_loader**，但這台電腦仍安裝呼叫舊 API
的 visdcc。這不是 `TW Affairs` 77 節點／81 關係資料損壞。

Hosted 新環境中真實 Jaal WSGI 於 2026-11-02 使用
`dash==4.5.0`、`visdcc==0.0.63`、`jaal==0.1.9`
通過（該環境的 `dash-bootstrap-components==0.13.1` 由 pip 解析器
選出），因此**現代 Dash 不必為此降回 Dash 2**。
先在有問題的 Windows **與啟動 8059 同一個 Python** 執行：

```bat
python -m pip show dash visdcc jaal dash-bootstrap-components
python -m pip install --upgrade "visdcc==0.0.63"
python -m pip check
python -m BertScript.jaal_runtime_diagnostics --root "TW Affairs"
```

這個 pip 指令會變更目前 Python 環境（若在 Anaconda `base`
也會影響同環境其他應用），**先關閉服務、確認套件版本及
環境用途**；若其他應用不能共用更新，改用獨立環境。
**不要把 `visdcc==0.0.63` 安裝到 Dash 2 的舊環境**：新版
visdcc 本身需要 Dash >=3。已正常工作的舊電腦無須升級。

新的輕量 `check_dash_visdcc_compatibility` 在真正匯入 Jaal
以前只讀取套件 metadata，對 Dash >=3 + visdcc <0.0.63
提供明確修復指令；Dash <3 + visdcc >=0.0.63 也提前告知
需分離環境，不會嘗試 monkeypatch 已移除的 Dash API。
它是**特定已驗證相容性邊界**的預檢，不代表所有未測套件版本
自動通過 Windows GUI 驗收，也不會安裝／修改任何套件。


### Jaal 根類別輸入框：同行緊湊排版

根類別控制列以 `根類別（英文 ClassLabel）：` 與輸入框、
`載入 Jaal` 按鈕排列在同一 flex row，輸入框桌面寬 320px
（避免瀏覽器全寬延伸造成空白），窄視窗時容許換行與縮小，
並用 `htmlFor` 連結可存取標籤。不修改 `JaalOriginalRoot`、
`btn_JaalOriginalLoad` 或 `JaalOriginalLargeConsent` ID 與
任何建圖／callback／子樹大小限制。Hosted `_dash-layout` 測試
驗證控件相鄰、寬度、響應式換行及預設 ClassLabel；實際不同
Windows 瀏覽器寬度仍需視覺驗證。


### 根類別可搜尋選單及階層收攏的非跳躍式展開

Jaal 根類別使用可搜尋單選 `dcc.Dropdown`，預選 `TW Affairs`，
支援英文 ClassLabel 關鍵字（不分大小寫）的局部文字查找。
選項從原本 authoritative `TopicTree.csv` / `TopicTree_AK4.csv`
組成的 `load_graph()[1]` 取得，排序後每次最多傳 80 項；
已選根類別始終保留在候選中以免篩選造成清空。候選清單的
Dash callback 不建立 Jaal 子程式、不執行分類模型或 WorkPool；
仍需按「載入 Jaal」才會真正建圖，250 節點的確認機制不變。

階層（收攏）仍只用可見節點佈局；但 `vis.Network.fit()`
**只在首次進入收攏階層**時調整視野，之後點擊展開或收回
一層時不再全圖自動縮放／重新置中，保持使用者的瀏覽焦點。
網狀（收攏）原本的佈局和視角行為維持不變。
Hosted tests 檢查 Dropdown 的 Dash layout/callback、真實分類節點選項、
前端 vis.DataSet 及 fit 次數；Windows Chrome 的實際視覺手感
仍需由使用者實機確認。


### 階層（收攏）增量展開：連續移動、不要跳閃（Windows 驗收待確認）

先前取消每次節點展開時的 `vis.Network.fit()` 只能固定鏡頭，
**無法**阻止階層 LayoutEngine 因可見節點集合改變而將原有節點直接移位。
同埠 Jaal 現在在每次階層收攏的展開／收合操作，先取得瀏覽器實際
`net.getPositions()` 目前顯示的座標；更新可見 DataSet 後取得
階層引擎算出的**目標**座標，再以 vis-network 既有
`net.body.nodes` 中的繪製座標**批次**放回舊位置，每個影格只呼叫
一次 `net.redraw()`（不用會逐節點重繪的 `moveNode()`）。新增子節點
由最近的已可見父／祖先座標出發，透過
`requestAnimationFrame` 與 460ms ease-out 漸進移到新目標。
允許新節點最初重疊，隨動畫逐漸分開。原階層的上下層、框狀標籤、
跨父邊仍由既有布局演算法決定，沒有啟用可能造成連續漂移的
`hierarchicalRepulsion` physics，也不會在每次展開改變 camera pan/zoom。
首次進入階層收攏仍維持原本的一次 `fit`。

當使用者快速連點、切換網狀／全展開、切換來源時，舊動畫會取消
並由目前畫面位置開始新動作，避免舊幀移動已切走的節點；瀏覽器
偏好 `prefers-reduced-motion: reduce` 時不啟動插值動畫。
無 `requestAnimationFrame` 或已知 `net.body.nodes`／`redraw` 介面時安全退回原階層排列；
此內部介面依賴需隨 visdcc／vis-network 升級重新驗證。
只處理**同埠 Jaal 階層（收攏）**，原始資料、分類樹與 WorkPool 不變，
網狀（收攏）仍保持原本物理佈局。Node mock 測試確認舊節點在
展開當下的座標不變、新子節點從父節點出發、77 節點時每影格單次重繪、模式切換可取消，
但不代表 Windows 真實 Chrome 與 77／81 子圖的視覺流暢度已驗收。


### Jaal 中文標籤開關（ClassTable CT；英文 fallback）

同 port Jaal 檢視器的圖形工具列增加「優先顯示中文名稱（無翻譯時顯示英文）」
開關，**預設關閉**，維持完整英文 ClassLabel。開啟時只從
`ClassesTree/data/ClassTable.csv` 取與本次已載入子圖節點 ID **完全相符**
的 `CT` 顯示名稱；ClassTable 不存在該列、`CT` 空白或只有空格時，
該節點仍顯示原本英文名稱。四種網狀／階層、全展開／收攏模式皆適用；
收攏子孫計數繼續顯示在標籤最後一行。

為保護既有 Jaal 行為，翻譯只放在 iframe 局部的 `dcc.Store`，
透過固定、不可插入 CSV 程式碼的 `graph.run` JS 在畫布內投影；
`graph.data` 的 `id`、原始 `title`、邊、Search／Filter／Color／Size
callback 皆不變。搜尋仍比對**完整英文 ClassLabel**，切換語言
不會重建 Jaal 子圖或修改任何 taxonomy CSV、WorkPool。
只有使用者按「載入 Jaal」並建立子視窗時才讀取 ClassTable，
同一子圖只傳輸已載入節點的翻譯。手動編輯 ClassTable 後需重新啟動
8059 Python 服務才能更新已快取的翻譯；Windows 真實視覺驗收待確認。
