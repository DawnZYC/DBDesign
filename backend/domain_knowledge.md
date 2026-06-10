# SG-TIMES / EcoTEA WP1 领域知识

> 本文档作为 RAG 知识源之一，灌入 ChromaDB（按 H2 切段）。
> 写新内容请保持每段 200-500 字，主题单一。

## 单位换算 — 能源单位

能源单位之间的换算关系（按 IEA 标准）：

- 1 PJ (petajoule, 10^15 J) ≈ 23.885 ktoe (千吨油当量)
- 1 ktoe ≈ 0.041868 PJ
- 1 GWh (gigawatt-hour) = 0.0036 PJ
- 1 PJ = 277.778 GWh
- 1 MWh = 3.6 GJ = 0.0036 PJ
- 1 kWh = 3.6 MJ

EcoTEA / SG-TIMES 模型里能源类商品（commodity_set = NRG）默认单位是 **PJ**；
电力相关有时用 GWh / MWh，注意换算。

## 单位换算 — CO₂ 排放

- kt-CO₂ (千吨二氧化碳) — SG-TIMES 模型里排放类商品（commodity_set = ENV）的标准单位
- 1 Mt-CO₂ = 1000 kt-CO₂
- 排放因子（Emission Factor）单位通常是 kg-CO₂ / GJ 或 kt-CO₂ / PJ
- 1 kg-CO₂ / GJ = 1 kt-CO₂ / PJ（数值相同）

注意：CO₂ 量纲不能直接转能量单位。在做"每 PJ 排放多少 kt-CO₂"时，要乘以排放因子。

## 单位换算 — 货币

EcoTEA WP1 数据使用 **MSGD2016**（2016 年新加坡元）作为基准货币。
- CAPEX 单位常见：M$ / GW（每 GW 装机的百万美元投资）
- Fixed OPEX 单位：M$ / GW-yr（每 GW-yr 的百万美元固定运维）
- Variable OPEX 单位：M$ / PJ（每 PJ 输出的百万美元变动运维）

## SG-TIMES Commodity Set — NRG 能源商品

NRG (Energy commodities) 表示能源类商品，是技术消耗或产出的能源载体：

- **PWRCOA** Power Coal — 发电用煤
- **PWRPCK** Power Pet-coke — 发电用石油焦
- **PWRNGA** Power Natural Gas — 发电用天然气
- **PWRHFO** Power Fuel Oil — 发电用重燃油
- **PWRDSL** Power Diesel — 发电用柴油
- **PWRWAS** Power Waste — 发电用废弃物
- **PWRBMS** Power Biomass — 发电用生物质
- **PWRURA** Power Uranium — 发电用铀
- **PWRSOL** Power Solar — 太阳能
- **PWRHYD** Power Hydrogen — 氢能
- **WTEEEC** Incineration Electricity — 焚烧产电
- **PWRRTFNGA** NGA consumption by retrofitted plant — 改造电厂耗气

## SG-TIMES Commodity Set — ENV 排放商品

ENV (Environmental commodities) 表示排放类商品（虚拟商品，量纲是排放当量）：

- **PWRCO2** Power Carbon Dioxide — 发电直接排放的 CO₂
- **PWRCO2C** Power CO₂ from CCS — 经 CCS 捕集的 CO₂
- **PWRCAPTURECO2** Dummy CO₂ Capture by PWR CCS — CCS 捕集占位
- **PWRCO2S** Power CO₂ Storage from CCS — CCS 储存
- **PWRCO2U** Power CO₂ Utilization from CCS — CCS 利用
- **PWRRTFCO2** CO₂ emission from retrofitted plant — 改造电厂排放

## 行业 Sector 对照

EcoTEA WP1 模型涵盖 10 个行业（与 Excel 文件 sheet 对应）：

- **POWER** 电力（Power）— 发电、热电联产
- **INDUSTRY** 工业（Industry）— 化工、炼油、钢铁等耗能产业
- **PRIMARY** 一次能源（Primary）— 进口煤 / 油 / 气等
- **TRANSPORT** 交通（Transport / Transportation）— 客运、货运、航运
- **WATER** 水务（Water）— 海水淡化、再生水
- **WASTE** 废弃物（Waste）— 垃圾分类、焚烧
- **BUILDING** 建筑（Building）— 商业建筑暖通空调、照明
- **HOUSEHOLD** 家庭（Household）— 居民侧用电、热水器、冰箱等
- **AGRI** 农业（Agriculture / Agrifood）— 农业、食品行业能耗
- **INFOCOMM** 信息通信（InfoComm / ICT）— 数据中心、电信设施

## 时间片层级 CTSLvl

CTSLvl (Commodity Time-Slice Level) 表示该商品需要按多细的时间粒度建模：

- **DAYNITE** — 一天分昼夜两段；用于电力等强日内变化的商品
- **SEASON** — 按四季划分
- **WEEKLY** — 工作日 / 周末
- **ANNUAL** （默认）— 全年合计，无时间粒度

EcoTEA Power 模型里 WTEEEC（焚烧产电）和 PWRRTFCO2（改造电厂排放）是 DAYNITE 级别。

## CCS 路径术语

碳捕获、利用与封存（CCS / CCUS）相关概念：

- **Capture** 捕集：从烟气中分离 CO₂
- **Storage** 封存：把捕集的 CO₂ 注入地下永久封存
- **Utilization** 利用：把 CO₂ 用于生产化工品、混凝土等
- 在 SG-TIMES 里通过 PWRCAPTURECO2 → PWRCO2C → (PWRCO2S | PWRCO2U) 这条流转链路建模

## 技术代码命名规则

EcoTEA WP1 的 technology_code 一般是 11 位字符，遵循约定：

- 前 3 位：所属过程类别（PWR=发电、IRF=炼油、HHD=家庭、TRP=交通、AFV=农业等）
- 中间 3 位：燃料 / 介质（NGA=天然气、COA=煤、ELE=电、SOL=太阳能等）
- 末 3 位：技术形式或代号（CCF=combined cycle F class、CCH=H class、CGP=cogen plant 等）
- 后缀 2 位：版本 / 启用年份编号（00 / 26 / 11 等）

例：
- PWRNGACCF01 = Power × Natural gas × Combined Cycle F class × 版本 01
- IRFELECAE00 = Industry refinery × Electricity × Compressed Air Equipment × 版本 00
