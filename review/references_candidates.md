# 参考文献候选清单（F 题，联网核实版）

- 整理：Claude 子代理，2026-11-21
- 核实方式：每条都联网打开了元数据页。外文期刊、会议和图书以 Crossref API（`https://api.crossref.org/works/<DOI>`，即出版社注册的 DOI 元数据，属一手）为主，标题、作者、卷期、页码逐字段对照。摘要取自出版社文章页的 `dc.description` 元标签（一手）。中文期刊取自期刊官网或文献平台条目。
- **核实范围：只核实了题录字段和摘要，没有读任何一篇全文。**“可引用于”中有关文章内容的说法，凡是摘要里没有的，都标了“内容未核实”。
- 格式：GB/T 7714—2015 顺序编码制。作者超过 3 人时写前 3 人，后加“等”或“et al”。
- 论文现有参考文献（`paper/初稿/08_灵敏度与评价.md`）已有 3 条：[1] Gurobi 手册、[2] OR-Tools CP-SAT、[3] Hooker & Ottosson 2003。下面第 8 条 Gurobi 与现有 [1] 重复，给出的是更规范的写法，可以替换。
- 章节号按 `paper/初稿/` 当前标题：一 问题重述，五 共用模块，七 问题 2（字典序整数规划），八 问题 3（路线枚举与事件回放排程），九 问题 4（联合邻域搜索），十一 模型检验与评价。

正式清单 10 条（[1]–[10]），另有 5 条已核实的备选。

---

## 一、带取送的车辆路径问题（PDP / VRPPD）

### [1] Savelsbergh & Sol 1995（经典定义论文）

Savelsbergh M W P, Sol M. The general pickup and delivery problem[J]. Transportation Science, 1995, 29(1): 17-29. DOI: 10.1287/trsc.29.1.17.

- 核实：Crossref https://api.crossref.org/works/10.1287/trsc.29.1.17 （INFORMS 注册，一手）。标题、作者、刊名、1995 年、29 卷 1 期、17-29 页均一致。
- 可引用于：第二章 2.2 建模思路、第八章 8.1 批内路线枚举，作为“每批路线属于带取送的车辆路径问题”这一问题类别的经典出处。只引用其问题类别名称，不涉及内容细节。

### [2] Parragh, Doerner & Hartl 2008（综述 Part I：仓库与客户之间的运输）

Parragh S N, Doerner K F, Hartl R F. A survey on pickup and delivery problems. Part I: Transportation between customers and depot[J]. Journal für Betriebswirtschaft, 2008, 58(1): 21-51. DOI: 10.1007/s11301-008-0033-7.

- 核实：Crossref https://api.crossref.org/works/10.1007/s11301-008-0033-7 （Springer，一手）。摘要取自 Springer 文章页 https://link.springer.com/article/10.1007/s11301-008-0033-7 的元标签（一手）。
- 摘要原文要点：该文讨论把货物从仓库运往 linehaul 客户、从 backhaul 客户运回仓库的问题类（VRPB），包括 mixed linehauls and backhauls，以及 VRPDDP（同时有送货和取货需求的客户可以被访问两次）。
- 可引用于：第八章 8.1。本题中“接领”是仓库到单位，“送交”是单位到仓库，正好属于摘要所说的“客户与仓库之间运输”一类。“同一站点多次到访”可以对照摘要中的 VRPDDP。这是与本题结构最贴合的一篇。

## 二、多目标优化：字典序方法与归一化加权

### [3] Marler & Arora 2004（多目标方法综述）

Marler R T, Arora J S. Survey of multi-objective optimization methods for engineering[J]. Structural and Multidisciplinary Optimization, 2004, 26(6): 369-395. DOI: 10.1007/s00158-003-0368-6.

- 核实：Crossref https://api.crossref.org/works/10.1007/s00158-003-0368-6 （Springer，一手）。
- 可引用于：第七章 7.2 模型的字典序目标（先批次最少，再代领代交量最少），作为多目标方法分类的综述出处。
- **内容未核实**：“该综述专门讨论了字典序法”这一点没有在可打开的页面上看到原文。目前只能确认：Springer 文章页的参考文献表里有 Rentmeesters M J, Tsai W K, Lin K J 1996 “A theory of lexicographic multi-criteria optimization”。引用前请翻原文确认有字典序法的小节；如果没有，就改用备选 B4（Ehrgott 教材）。

### [4] Marler & Arora 2005（目标函数变换与归一化）

Marler R T, Arora J S. Function-transformation methods for multi-objective optimization[J]. Engineering Optimization, 2005, 37(6): 551-570. DOI: 10.1080/03052150500114289.

- 核实：Crossref https://api.crossref.org/works/10.1080/03052150500114289 （Taylor & Francis 注册，一手）。标题、两位作者、刊名、2005 年 9 月、37 卷 6 期、551-570 页均一致。最初是从 [B3] 的 Springer 页参考文献表中发现这篇的（那里写作 “Transformation methods for multi-objective optimization. Eng Optim 37:551–569”，题名和末页与 Crossref 略有出入，以 Crossref 为准）。
- 摘要只看到索引站的转述（bohrium、iaorifors，属二手），大意是：把各目标函数变换到相近的单位和量级；在加权和法下比较各种变换方法；指出简单归一化加修正的好处。
- 可引用于：第九章 9.2 模型和第八章 8.5 消融与合成方式，作为“各目标先做区间（极差）归一化，再等权加权”的方法依据。

## 三、局部搜索 / 大邻域搜索 / 多起点

### [5] Shaw 1998（提出大邻域搜索 LNS）

Shaw P. Using constraint programming and local search methods to solve vehicle routing problems[C]//Maher M, Puget J F. Principles and Practice of Constraint Programming — CP98: Lecture Notes in Computer Science, vol 1520. Berlin, Heidelberg: Springer, 1998: 417-431. DOI: 10.1007/3-540-49481-2_30.

- 核实：章节元数据见 Crossref https://api.crossref.org/works/10.1007/3-540-49481-2_30 （作者、题名、1998 年、417-431 页、Springer）。编者 Michael Maher、Jean-Francois Puget 见图书 DOI 的 Crossref 元数据 https://api.crossref.org/works/10.1007/3-540-49481-2 （editor 字段）。“LNCS, volume 1520”见 Springer 图书页 https://link.springer.com/book/10.1007/3-540-49481-2 的原始 HTML。以上均为一手。
- 可引用于：第九章 9.2 联合邻域搜索。注意本文用的是坐标下降、成对邻域加多起点，不是严格的“破坏—修复”式 LNS。引用时写成“邻域搜索思想参见”，不要声称实现了 LNS。

### [6] Ropke & Pisinger 2006（用 ALNS 求解带时间窗的取送问题）

Ropke S, Pisinger D. An adaptive large neighborhood search heuristic for the pickup and delivery problem with time windows[J]. Transportation Science, 2006, 40(4): 455-472. DOI: 10.1287/trsc.1050.0135.

- 核实：Crossref https://api.crossref.org/works/10.1287/trsc.1050.0135 （INFORMS，一手）。
- 可引用于：第八章 8.1 或第九章 9.2。它同时属于“PDP”和“邻域搜索”两类，正文中可用一句话说明区别：本文批内路线规模小、可以穷举，所以穷举而不用 ALNS。只引用题名所示的问题和方法，不涉及内容细节。

### [7] Martí, Resende & Ribeiro 2013（多起点方法综述）

Martí R, Resende M G C, Ribeiro C C. Multi-start methods for combinatorial optimization[J]. European Journal of Operational Research, 2013, 226(1): 1-8. DOI: 10.1016/j.ejor.2012.10.012.

- 核实：Crossref https://api.crossref.org/works/10.1016/j.ejor.2012.10.012 （Elsevier，一手）。
- 可引用于：第九章 9.5 搜索的稳定性，用于多起点局部搜索、起点数与结果稳定性的讨论。这里只依据题名，具体内容未核实。

## 四、混合整数规划求解器

### [8] Gurobi 参考手册 13.0 版

Gurobi Optimization, LLC. Gurobi optimizer reference manual: version 13.0[EB/OL]. [2026-11-21]. https://docs.gurobi.com/projects/optimizer/en/13.0/.

- 核实：Gurobi 官方“如何引用”页 https://support.gurobi.com/hc/en-us/articles/360013195592 （一手）推荐的 BibTeX 是：author = {Gurobi Optimization, LLC}；title = {Gurobi Optimizer Reference Manual}；year = 2026；url = https://www.gurobi.com。13.0 版手册页 https://docs.gurobi.com/projects/optimizer/en/13.0/index.html （一手）写明 “This is the manual for version 13.0 of the Gurobi Optimizer”。当前 current 版本已是 14.0，所以 URL 要固定到 13.0，与 evidence.md 中记录的 Gurobi 13.0.0 一致。
- 13.0 手册的发布年份未核实，所以上面只写了引用日期，没有写出版年。如果想和官方 BibTeX 保持一致，也可以写成：Gurobi Optimization, LLC. Gurobi optimizer reference manual[EB/OL]. (2026)[2026-11-21]. https://www.gurobi.com.
- 可引用于：第七章 7.2、7.3（字典序 MILP 求解，MIPGap=0），以及第八章 8.4 和附录中的证书计算。

## 五、物资调运 / 应急与军事物资配送（中文）

### [9] 刘春林、施建军、何建敏 2001（应急物资调度：先求时间最早，再求出救点最少）

刘春林, 施建军, 何建敏. 一类应急物资调度的优化模型研究[J]. 中国管理科学, 2001, 9(3): 29-36.

- 核实：文献平台条目 https://search.napstic.cn/literature/periodical/010zgglkx200103005 。对该页原始 HTML 做 grep，可以直接看到 `"year":2001,"volume":"9","issue":"3","page":"29-36"`，作者顺序为刘春林、施建军、何建敏，英文题名为 “The Study on Optimal Model for a Kind of Emergency Material Dispatch Problem”，基金号为国家自然科学基金 79970096。
- **这是聚合平台的条目，不是期刊官网**，算半一手：页面数据完整，但来源不是出版方。在《中国管理科学》官网没有检索到该文，DOI 未核实，这篇老文章大概率没有 DOI。建议交稿前在知网再核一次。
- 可引用于：第七章 7.2。该文摘要说“在应急时间最早的前提下，使出救点数目最少”，这是分层（字典序）目标在国内物资调度文献中的先例，和本文“先批次最少，再代领代交量最少”结构相同。也可以放在第一章 1.1 背景中。

### [10] 赵文飞、周刚、杨树杰、董超 2015（带时间窗的军事物资配送）

赵文飞, 周刚, 杨树杰, 等. 带时间窗军事物资配送问题的NSGA-Ⅱ算法[J]. 系统工程与电子技术, 2015, 37(11): 2513-2519. DOI: 10.3969/j.issn.1001-506X.2015.11.14.

- 核实：期刊官网页 https://www.sys-ele.com/CN/Y2015/V37/I11/2513 （一手）。
  - 原始 HTML 的 citation 元标签给出：卷 37、期 11、首页 2513、末页 2519、DOI 10.3969/j.issn.1001-506X.2015.11.14。
  - 题名和四位作者（依次为赵文飞、周刚、杨树杰、董超）是在页面正文中 grep 到的；元标签里没有 citation_author 字段。
  - https://doi.org/10.3969/j.issn.1001-506X.2015.11.14 会跳转到该刊官网。
  - 年份 2015 来自卷期和 DOI。该页 citation_date 标签写的是 “2010-01-03”，明显是网站的默认值，不予采信。
- 可引用于：第一章 1.1 背景，说明车辆路径问题在军事物资配送中的应用。也可以放在第十一章 11.4 推广，与本文对照：该文用 NSGA-Ⅱ 求 Pareto 前沿，本文用字典序加归一化加权。

---

## 已核实的备选（可替换正文条目）

- **[B1]** Berbeglia G, Cordeau J F, Gribkovskaia I, et al. Static pickup and delivery problems: a classification scheme and survey[J]. TOP, 2007, 15(1): 1-31. DOI: 10.1007/s11750-007-0009-0.
  - 核实：Crossref https://api.crossref.org/works/10.1007/s11750-007-0009-0 ；摘要取自 Springer 文章页元标签（一手）。摘要写的是：给出一个能刻画大量取送问题的通用框架和三字段分类法，并综述了求解方法。
  - 可引用于：第八章 8.1，作为 PDP 分类的出处。
- **[B2]** Parragh S N, Doerner K F, Hartl R F. A survey on pickup and delivery problems. Part II: Transportation between pickup and delivery locations[J]. Journal für Betriebswirtschaft, 2008, 58(2): 81-117. DOI: 10.1007/s11301-008-0036-4.
  - 核实：Crossref https://api.crossref.org/works/10.1007/s11301-008-0036-4 的 subtitle 字段，以及 doi.org 内容协商返回的 BibTeX，两处都给出完整副标题（一手）。
  - 本题是仓库与单位之间的运输，Part I（即 [2]）更贴合，所以 Part II 只列作备选。
- **[B3]** Marler R T, Arora J S. The weighted sum method for multi-objective optimization: new insights[J]. Structural and Multidisciplinary Optimization, 2010, 41(6): 853-862. DOI: 10.1007/s00158-009-0460-7.
  - 核实：Crossref https://api.crossref.org/works/10.1007/s00158-009-0460-7 （一手）。在线发表于 2009-12-12，纸本为 2010 年 6 月。
  - 摘要转述（二手）：讨论权重在偏好、Pareto 集和目标值上的含义，指出先验给定权重的固有缺陷，并给出避免误用的建议。摘要中没有提到归一化。
  - 可引用于：第十一章 11.3 局限，说明“等权加权”的局限。
- **[B4]** Ehrgott M. Multicriteria optimization[M]. 2nd ed. Berlin, Heidelberg: Springer, 2005. DOI: 10.1007/3-540-27659-9.
  - 核实：Crossref https://api.crossref.org/works/10.1007/3-540-27659-9 给出题名、出版社、2005 年和 ISBN 3540213988，但没有作者字段。Open Library https://openlibrary.org/isbn/9783540213987.json 给出 “2nd ed. edition”，作者条目 https://openlibrary.org/authors/OL3178342A.json 为 “Matthias Ehrgott”。Open Library 不是出版社页面，属二手。
  - 字典序最优在哪一章未核实（两个目录页分别返回 403 和连接中断）。
  - 可引用于：第七章 7.2。如果 [3] 原文中没有字典序法的小节，用本书替换 [3]。
- **[B5]** Battarra M, Cordeau J F, Iori M. Pickup-and-delivery problems for goods transportation[M]//Toth P, Vigo D. Vehicle routing: problems, methods, and applications. 2nd ed. Philadelphia: SIAM, 2014: 161-191. DOI: 10.1137/1.9781611973594.ch6.
  - 核实：章节和图书的 Crossref 元数据（一手）。
  - 字段说明：“2nd ed.”未在 Crossref 中看到，属未核实字段，使用时可删去。
  - 可用作 [2] 之外较新的 PDP 综述。

## 建议的最小引用集

篇幅紧时可以只用 8 条：[1][2][3][4][6][7][8][9]。

## 查过但放弃的候选

| 候选 | 原因 |
|---|---|
| 《军事应急物流中的物资调度多目标优化模型研究》（《物流工程与管理》，2015） | 只出现在搜索引擎的概括中，没有打开任何题录页，作者和卷期都无法核实 |
| 《系统工程理论与实践》《军事运筹与系统工程》中的军事物资配送论文 | 检索没有命中可以打开的题录页 |
| Pisinger & Ropke, Large neighborhood search（Handbook of Metaheuristics 中的章节） | 没有检索核实；[5][6] 已经覆盖 LNS，不要凭记忆补写 |
| dblp 的 CP98 题录 | dblp 对自动访问返回人机验证页，改用 Crossref 和 Springer 核实编者与卷号 |
