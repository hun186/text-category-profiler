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