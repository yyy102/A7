# 信息抽取与知识图谱构建系统

这是一个从零搭建的 Python Streamlit 课堂实验应用，对应 `project_requirment.txt` 中的信息抽取与知识图谱构建要求。

## 已实现模块

1. 命名实体识别与 BIO 标注
   - 支持英文与中文文本输入。
   - 使用 spaCy 中英文模型抽取人物、组织、地点三类实体。
   - 合并课程词典与规则结果，提升示例与课堂任务覆盖率。
   - 默认展示实体高亮。
   - 勾选“查看底层 BIO 标注”后展示 Token 与 BIO Tag 序列。
   - 支持嵌套实体候选展示，例如 `University of California, Los Angeles` 与 `Los Angeles`。

2. 实体关系抽取
   - 在 spaCy 实体识别结果基础上抽取主体、关系、客体三元组。
   - 支持创立、领导、任职、位于、收购、合作、出生于等常见关系。
   - 对同一句中没有明确触发词的实体对，可生成 `RELATED_TO` 兜底边，避免新文本下图谱为空。
   - 结果用表格展示 Subject、Predicate、Object 和证据句。

3. 知识图谱交互可视化
   - 将 entities 转换为 nodes。
   - 将 relations 转换为 edges。
   - 使用 vis-network.js 渲染网络图。
   - 节点按实体类型使用不同颜色和形状。
   - 边带箭头和关系标签。
   - 支持拖拽节点、滚轮缩放、悬停提示。

## 依赖说明

Python 包写在 `requirements.txt` 中：

```text
streamlit==1.45.1
spacy>=3.8.0,<3.9.0
en_core_web_sm-3.8.0
zh_core_web_sm-3.8.0
```

应用还使用以下标准库，不需要额外安装：

- `html`
- `json`
- `re`
- `dataclasses`
- `pathlib`
- `typing`

前端知识图谱库：

- `vis-network.js`
- 通过 `app.py` 中的 CDN 地址加载：`https://unpkg.com/vis-network/standalone/umd/vis-network.min.js`
- 因为它在浏览器端加载，所以不需要写入 Python requirements。

## 项目结构

```text
A7/
├── app.py                  # Streamlit 主程序
├── style.css               # 页面样式，可继续修改 UI 风格
├── requirements.txt        # Python 依赖，Streamlit Cloud 会自动读取
├── runtime.txt             # Streamlit Cloud Python 版本
├── README.md               # 项目说明
├── project_requirment.txt  # 原始项目要求
└── .streamlit/
    └── config.toml         # Streamlit 主题配置
```

## 运行方式

```powershell
cd D:\上财\NLP\A7
D:\Anaconda\Scripts\streamlit.exe run app.py
```

如果使用全新 Python 环境：

```powershell
pip install -r requirements.txt
streamlit run app.py
```

如果本地模型缺失，可手动安装：

```powershell
python -m spacy download en_core_web_sm
python -m spacy download zh_core_web_sm
```

## 示例输入

```text
Steve Jobs founded Apple in California. Apple is headquartered in Cupertino, and Tim Cook leads Apple. Microsoft partnered with OpenAI.
```

```text
马云创立阿里巴巴，阿里巴巴总部位于杭州。张一鸣创建字节跳动，字节跳动在北京与腾讯展开合作。
```

## UI 风格

界面参考 Facebook 的蓝白浅灰风格：

- 蓝色主操作按钮
- 浅灰页面背景
- 白色内容面板
- 圆形应用标识
- 紧凑、清晰的信息流式布局

后续如果需要继续修改 UI，优先编辑 `style.css` 中的颜色变量：

```css
--fb-blue: #1877f2;
--fb-bg: #f0f2f5;
--fb-card: #ffffff;
--fb-text: #050505;
```
