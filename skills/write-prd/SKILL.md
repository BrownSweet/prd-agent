---
name: write-prd
description: 识别单一或复合产品类型，并基于已确认结构化需求生成或修订完整PRD。用于管理后台、C端、API、数据产品、中台平台和硬件产品的类型判断、模板适配、PRD撰写及终审问题修复。
---

# PRD撰写

## 类型识别

选择一个主类型，可选择多个次类型：

- A：管理后台、CMS、Admin端。
- B：App、小程序、H5等C端应用。
- C：API、微服务、SDK。
- D：BI看板、报表、数据分析。
- E：支付中台、用户中心、策略引擎等平台。
- F：IoT、智能设备和嵌入式。

先输出类型、匹配特征和理由。不要自动确认类型。

## PRD生成

1. 只使用已确认结构化需求和产品类型。
2. 按固定九章模板生成完整PRD。
3. 为每个功能提供字段规格、交互步骤、唯一业务规则和页面状态。
4. 业务规则使用稳定 `R-XXX` 编号。
5. 不确定信息明确标记待确认，不自行补充业务能力。
6. 修订时只修复终审指出的问题，保留其他已确认内容。

阅读 [references/product-types.md](references/product-types.md) 和
[references/prd-template.md](references/prd-template.md)。

