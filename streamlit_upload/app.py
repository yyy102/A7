from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import streamlit as st
import streamlit.components.v1 as components


VIS_NETWORK_CDN = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"
BASE_DIR = Path(__file__).resolve().parent
STYLE_PATH = BASE_DIR / "style.css"

# Google Material colour palette for entity types
TYPE_META = {
    "PER":  {"label": "Person",       "zh": "人物", "color": "#1a73e8", "soft": "#e8f0fe"},
    "ORG":  {"label": "Organization", "zh": "组织", "color": "#137333", "soft": "#e6f4ea"},
    "LOC":  {"label": "Location",     "zh": "地点", "color": "#f9ab00", "soft": "#fef7e0"},
    "MISC": {"label": "Other",        "zh": "其他", "color": "#7b1fa2", "soft": "#f3e8fd"},
}

RELATION_LABELS = {
    "FOUNDER_OF":     "创立 / founded",
    "LEADS":          "领导 / leads",
    "WORKS_FOR":      "任职 / works for",
    "LOCATED_IN":     "位于 / located in",
    "ACQUIRED":       "收购 / acquired",
    "PARTNERED_WITH": "合作 / partnered with",
    "BORN_IN":        "出生于 / born in",
    "RELATED_TO":     "相关 / related to",
}

SPACY_MODEL_BY_LANGUAGE = {
    "英文 en_core_web_sm": "en_core_web_sm",
    "中文 zh_core_web_sm": "zh_core_web_sm",
}

SPACY_LABEL_MAP = {
    "PERSON": "PER",
    "PER":    "PER",
    "ORG":    "ORG",
    "GPE":    "LOC",
    "LOC":    "LOC",
    "FAC":    "LOC",
}

ENTITY_LEXICON = {
    "PER": [
        "Steve Jobs", "Tim Cook", "Bill Gates", "Satya Nadella", "Sam Altman",
        "Elon Musk", "Mark Zuckerberg", "Jack Ma",
        "马云", "张一鸣", "雷军", "王兴",
        "史蒂夫·乔布斯", "比尔·盖茨", "萨姆·奥特曼", "埃隆·马斯克",
    ],
    "ORG": [
        "University of California, Los Angeles", "University of California",
        "OpenAI", "Microsoft", "Apple Inc.", "Apple", "Google", "Alphabet",
        "Tesla", "SpaceX", "Meta", "Facebook", "Amazon", "Nvidia",
        "Alibaba", "Tencent", "ByteDance", "Meituan", "UCLA",
        "苹果公司", "微软", "阿里巴巴", "腾讯", "字节跳动", "美团", "小米",
        "清华大学", "北京大学",
    ],
    "LOC": [
        "Los Angeles", "San Francisco", "Silicon Valley", "New York",
        "Seattle", "Cupertino", "Palo Alto", "California", "Beijing",
        "Shanghai", "Shenzhen", "Hangzhou", "China", "United States",
        "北京", "上海", "深圳", "杭州", "中国", "美国", "加州", "洛杉矶", "硅谷",
    ],
}

SAMPLES = {
    "英文示例：创业关系": (
        "Steve Jobs founded Apple in California. Apple is headquartered in "
        "Cupertino, and Tim Cook leads Apple. Microsoft partnered with OpenAI."
    ),
    "英文示例：嵌套实体": (
        "Researchers at University of California, Los Angeles worked with "
        "Microsoft in Seattle. Los Angeles is also a location entity."
    ),
    "中文示例：商业新闻": (
        "马云创立阿里巴巴，阿里巴巴总部位于杭州。张一鸣创建字节跳动，"
        "字节跳动在北京与腾讯展开合作。"
    ),
}


@dataclass(frozen=True)
class Entity:
    text: str
    label: str
    start: int
    end: int
    source: str = "rule"

    @property
    def label_name(self) -> str:
        meta = TYPE_META.get(self.label, TYPE_META["MISC"])
        return f"{meta['zh']} / {meta['label']}"


@dataclass(frozen=True)
class Relation:
    source: str
    target: str
    relation: str
    evidence: str

    @property
    def label_name(self) -> str:
        return RELATION_LABELS.get(self.relation, self.relation)


def case_aware_find(text: str, phrase: str) -> Iterable[tuple[int, int]]:
    flags = 0 if re.search(r"[\u4e00-\u9fff]", phrase) else re.IGNORECASE
    pattern = re.escape(phrase)
    if phrase.isascii() and re.search(r"[A-Za-z0-9]", phrase):
        pattern = rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"
    for match in re.finditer(pattern, text, flags):
        yield match.start(), match.end()


def add_regex_entities(text: str) -> list[Entity]:
    entities: list[Entity] = []
    org_pattern = re.compile(
        r"\b[A-Z][A-Za-z&]*(?:\s+(?:of|and|the|[A-Z][A-Za-z&]*|"
        r"[A-Z][A-Za-z&]*,))*\s+"
        r"(?:University|Company|Corporation|Corp\.|Inc\.|Labs|Technologies)\b"
    )
    for match in org_pattern.finditer(text):
        value = match.group().strip()
        if len(value) > 4:
            entities.append(Entity(value, "ORG", match.start(), match.end(), "regex"))

    person_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b")
    blocked = {"Los Angeles", "San Francisco", "New York", "Silicon Valley"}
    for match in person_pattern.finditer(text):
        value = match.group().strip()
        if value not in blocked and value not in ENTITY_LEXICON["ORG"]:
            entities.append(Entity(value, "PER", match.start(), match.end(), "regex"))
    return entities


def extract_entities(text: str) -> list[Entity]:
    entities: list[Entity] = []
    for label, phrases in ENTITY_LEXICON.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            for start, end in case_aware_find(text, phrase):
                entities.append(Entity(text[start:end], label, start, end, "lexicon"))

    entities.extend(add_regex_entities(text))
    unique: dict[tuple[int, int, str, str], Entity] = {}
    for entity in entities:
        unique[(entity.start, entity.end, entity.label, entity.text.lower())] = entity
    return sorted(unique.values(), key=lambda item: (item.start, -(item.end - item.start)))


def detect_language_option(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "中文 zh_core_web_sm"
    return "英文 en_core_web_sm"


@st.cache_resource(show_spinner=False)
def load_spacy_model(model_name: str):
    import spacy
    return spacy.load(model_name)


def extract_entities_spacy(text: str, language_option: str) -> tuple[list[Entity], str]:
    model_name = SPACY_MODEL_BY_LANGUAGE[language_option]
    try:
        nlp = load_spacy_model(model_name)
    except ModuleNotFoundError:
        return extract_entities(text), "未安装 spaCy，已自动切换到规则兜底。"
    except OSError:
        return extract_entities(text), f"未安装 spaCy 模型 {model_name}，已自动切换到规则兜底。"

    doc = nlp(text)
    entities: list[Entity] = []
    for ent in doc.ents:
        label = SPACY_LABEL_MAP.get(ent.label_)
        if label is None:
            continue
        entities.append(Entity(ent.text, label, ent.start_char, ent.end_char, f"spacy:{ent.label_}"))

    entities.extend(extract_entities(text))
    unique: dict[tuple[int, int, str, str], Entity] = {}
    for entity in entities:
        unique[(entity.start, entity.end, entity.label, entity.text.lower())] = entity
    merged = sorted(unique.values(), key=lambda item: (item.start, -(item.end - item.start)))
    return merged, f"已使用 spaCy 模型 {model_name}，并合并课程词典补充结果。"


def select_flat_entities(entities: list[Entity]) -> list[Entity]:
    selected: list[Entity] = []

    def priority(entity: Entity) -> int:
        if entity.source == "lexicon":
            return 0
        if entity.source.startswith("spacy"):
            return 1
        return 2

    for entity in sorted(
        entities,
        key=lambda item: (-(item.end - item.start), item.start, priority(item)),
    ):
        if all(entity.end <= kept.start or entity.start >= kept.end for kept in selected):
            selected.append(entity)
    return sorted(selected, key=lambda item: item.start)


def nested_entities(entities: list[Entity]) -> list[Entity]:
    nested: list[Entity] = []
    for entity in entities:
        if any(
            other is not entity
            and other.start <= entity.start
            and other.end >= entity.end
            and (other.start, other.end) != (entity.start, entity.end)
            for other in entities
        ):
            nested.append(entity)
    return nested


def render_highlighted_text(text: str, entities: list[Entity]) -> str:
    parts: list[str] = []
    cursor = 0
    for entity in entities:
        parts.append(html.escape(text[cursor: entity.start]))
        meta = TYPE_META.get(entity.label, TYPE_META["MISC"])
        parts.append(
            "<span class='entity-chip' "
            f"style='--entity-bg:{meta['soft']};--entity-color:{meta['color']}'>"
            f"{html.escape(entity.text)}"
            f"<small>{html.escape(entity.label)}</small>"
            "</span>"
        )
        cursor = entity.end
    parts.append(html.escape(text[cursor:]))
    return "".join(parts).replace("\n", "<br>")


TOKEN_PATTERN = re.compile(
    r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]|[^\s]",
    re.UNICODE,
)


def token_bio_rows(text: str, entities: list[Entity]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for match in TOKEN_PATTERN.finditer(text):
        token = match.group()
        token_start, token_end = match.span()
        owner = next(
            (
                entity
                for entity in entities
                if token_start >= entity.start and token_end <= entity.end
            ),
            None,
        )
        if owner is None:
            tag = "O"
        else:
            prefix = "B" if token_start == owner.start else "I"
            tag = f"{prefix}-{owner.label}"
        rows.append({"Token": token, "BIO Tag": tag})
    return rows


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"[。！？.!?\n]+", text):
        end = match.end()
        sentence = text[start:end].strip()
        if sentence:
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            spans.append((start + leading, end, sentence))
        start = end
    tail = text[start:].strip()
    if tail:
        leading = len(text[start:]) - len(text[start:].lstrip())
        spans.append((start + leading, len(text), tail))
    return spans


def relation_from_pair(first: Entity, second: Entity, context: str, reverse: bool) -> str | None:
    middle = context.lower()
    if not reverse:
        if first.label == "PER" and second.label == "ORG":
            if re.search(r"found(ed|er)?|co-?founded|创立|创办|创建", middle):
                return "FOUNDER_OF"
            if re.search(r"ceo|leads?|领导|首席执行官|担任", middle):
                return "LEADS"
            if re.search(r"works? at|joined|任职|加入|就职", middle):
                return "WORKS_FOR"
        if first.label == "ORG" and second.label == "LOC":
            if re.search(r"based|headquarter|located|\bin\b|\bat\b|位于|总部|在", middle):
                return "LOCATED_IN"
        if first.label == "ORG" and second.label == "ORG":
            if re.search(r"acquir|收购", middle):
                return "ACQUIRED"
            if re.search(r"partner|collaborat|cooperat|合作|联合", middle):
                return "PARTNERED_WITH"
        if first.label == "PER" and second.label == "LOC":
            if re.search(r"born|出生", middle):
                return "BORN_IN"
    else:
        if first.label == "ORG" and second.label == "PER":
            if re.search(r"founded by|由.+创立|由.+创办|由.+创建", middle):
                return "FOUNDER_OF"
        if first.label == "LOC" and second.label == "ORG":
            if re.search(r"home to|hosts?|位于|坐落", middle):
                return "LOCATED_IN"
    return None


def extract_relations(
    text: str, entities: list[Entity], include_related: bool = False
) -> list[Relation]:
    relations: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()

    def add_relation(source: str, target: str, relation: str, evidence: str) -> None:
        key = (source.lower(), target.lower(), relation)
        if key not in seen:
            seen.add(key)
            relations.append(Relation(source, target, relation, evidence))

    for sent_start, sent_end, sentence in split_sentences(text):
        sentence_entities = [
            entity for entity in entities if entity.start >= sent_start and entity.end <= sent_end
        ]
        sentence_entities.sort(key=lambda item: item.start)

        for first, second in zip(sentence_entities, sentence_entities[1:]):
            context = text[first.end: second.start]
            relation = relation_from_pair(first, second, context, reverse=False)
            source, target = first.text, second.text
            if relation is None:
                relation = relation_from_pair(first, second, context, reverse=True)
                if relation == "FOUNDER_OF" and first.label == "ORG" and second.label == "PER":
                    source, target = second.text, first.text
                elif relation == "LOCATED_IN" and first.label == "LOC" and second.label == "ORG":
                    source, target = second.text, first.text
            if relation is not None:
                add_relation(source, target, relation, sentence)

        orgs = [entity for entity in sentence_entities if entity.label == "ORG"]
        for i, first in enumerate(orgs):
            for second in orgs[i + 1:]:
                if first.text.lower() == second.text.lower():
                    continue
                between_and_after = text[first.end: min(sent_end, second.end + 12)]
                has_partner_word = re.search(
                    r"partner|collaborat|cooperat|合作|联合", between_and_after, re.IGNORECASE
                )
                has_connector = re.search(r"with|and|与|和|同", between_and_after, re.IGNORECASE)
                if has_partner_word and has_connector:
                    add_relation(first.text, second.text, "PARTNERED_WITH", sentence)

        if include_related:
            for first, second in zip(sentence_entities, sentence_entities[1:]):
                if first.text.lower() == second.text.lower():
                    continue
                already_linked = any(
                    r.source.lower() == first.text.lower()
                    and r.target.lower() == second.text.lower()
                    for r in relations
                )
                if not already_linked:
                    add_relation(first.text, second.text, "RELATED_TO", sentence)
    return relations


def entity_rows(entities: list[Entity], nested: list[Entity]) -> list[dict[str, object]]:
    nested_keys = {(item.start, item.end, item.label) for item in nested}
    return [
        {
            "实体文本": entity.text,
            "类型": entity.label_name,
            "BIO 类型": entity.label,
            "位置": f"{entity.start}-{entity.end}",
            "嵌套候选": "是" if (entity.start, entity.end, entity.label) in nested_keys else "",
        }
        for entity in entities
    ]


def relation_rows(relations: list[Relation]) -> list[dict[str, str]]:
    return [
        {
            "主体 Subject":    relation.source,
            "关系 Predicate":  relation.label_name,
            "客体 Object":     relation.target,
            "证据句 Evidence": relation.evidence,
        }
        for relation in relations
    ]


def graph_payload(
    entities: list[Entity], relations: list[Relation]
) -> tuple[list[dict], list[dict]]:
    by_name: dict[str, Entity] = {}
    for entity in entities:
        key = entity.text.lower()
        current = by_name.get(key)
        if current is None or len(entity.text) > len(current.text):
            by_name[key] = entity

    nodes = []
    for key, entity in by_name.items():
        meta = TYPE_META.get(entity.label, TYPE_META["MISC"])
        nodes.append(
            {
                "id": key,
                "label": entity.text,
                "title": f"{entity.text} ({entity.label_name})",
                "group": entity.label,
                "color": {"background": meta["soft"], "border": meta["color"]},
                "font": {"color": "#202124", "size": 18, "face": "Arial"},
                "borderWidth": 2,
                "shape": "dot",
                "size": 25 if entity.label == "ORG" else 19,
            }
        )

    edges = []
    known_nodes = {node["id"] for node in nodes}
    for index, relation in enumerate(relations):
        source = relation.source.lower()
        target = relation.target.lower()
        if source in known_nodes and target in known_nodes:
            edges.append(
                {
                    "id": f"edge-{index}",
                    "from": source,
                    "to": target,
                    "label": relation.relation,
                    "title": relation.evidence,
                    "arrows": "to",
                    "color": {"color": "#5f6368", "highlight": "#1a73e8"},
                    "font": {"align": "middle", "size": 13, "color": "#202124", "face": "Arial"},
                }
            )
    return nodes, edges


def render_graph(nodes: list[dict], edges: list[dict]) -> None:
    if not nodes:
        st.info("暂无实体节点。输入文本后点击「抽取信息」即可生成图谱。")
        return

    graph_html = f"""
    <div id="kg-network"></div>
    <script src="{VIS_NETWORK_CDN}"></script>
    <script>
      const nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
      const edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
      const container = document.getElementById("kg-network");
      const options = {{
        autoResize: true,
        interaction: {{
          hover: true,
          tooltipDelay: 80,
          navigationButtons: true,
          keyboard: true,
          zoomView: true,
          dragNodes: true
        }},
        physics: {{
          enabled: true,
          solver: "forceAtlas2Based",
          forceAtlas2Based: {{
            gravitationalConstant: -74,
            centralGravity: 0.012,
            springLength: 150,
            springConstant: 0.08
          }},
          stabilization: {{ iterations: 140 }}
        }},
        nodes: {{
          shadow: {{ enabled: true, color: "rgba(26,115,232,.14)", size: 8, x: 0, y: 4 }}
        }},
        edges: {{
          smooth: {{ enabled: true, type: "dynamic" }},
          width: 2
        }},
        groups: {{
          PER:  {{ shape: "dot" }},
          ORG:  {{ shape: "database" }},
          LOC:  {{ shape: "diamond" }},
          MISC: {{ shape: "dot" }}
        }}
      }};
      new vis.Network(container, {{ nodes, edges }}, options);
    </script>
    <style>
      #kg-network {{
        height: 540px;
        width: 100%;
        border: 1px solid #dadce0;
        border-radius: 12px;
        background:
          radial-gradient(circle at 16px 16px, rgba(26,115,232,.06) 1px, transparent 0),
          #ffffff;
        background-size: 24px 24px;
        box-shadow: 0 1px 2px rgba(60,64,67,.15);
      }}
    </style>
    """
    components.html(graph_html, height=560, scrolling=False)


def inject_css() -> None:
    if STYLE_PATH.exists():
        st.markdown(
            f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("未找到 style.css，应用将使用 Streamlit 默认样式。")


def main() -> None:
    st.set_page_config(
        page_title="IE Knowledge Graph Lab",
        page_icon="📘",
        layout="wide",
    )
    inject_css()

    # ── Header ──────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="g-topbar">
          <div class="g-logo">IE</div>
          <div>
            <h1>信息抽取与知识图谱构建系统</h1>
            <p>NER 高亮、BIO 标注、关系抽取与可拖拽知识图谱的一体化实验台。</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Controls card under header ───────────────────────────────────────────
    with st.container(border=True):
        st.subheader("输入与选项")
        control_col_1, control_col_2, control_col_3 = st.columns([1.15, 1, 1], gap="large")

        with control_col_1:
            sample_name = st.selectbox("示例文本", list(SAMPLES.keys()))
            use_sample = st.button("填入示例", use_container_width=True)

        with control_col_2:
            st.markdown("<div class='control-mini-title'>抽取引擎</div>", unsafe_allow_html=True)
            backend = st.radio(
                "抽取引擎",
                ["spaCy 模型抽取", "规则抽取（兜底）"],
                index=0,
                label_visibility="collapsed",
            )
            language_choice = st.selectbox(
                "spaCy 语言模型",
                ["自动检测", "英文 en_core_web_sm", "中文 zh_core_web_sm"],
            )

        with control_col_3:
            show_bio = st.checkbox("查看底层 BIO 标注", value=False)
            show_nested = st.checkbox("显示嵌套实体候选", value=True)
            include_related = st.checkbox("无明确关系时生成 RELATED_TO 边", value=True)
            st.caption("推荐使用 spaCy 模型抽取；规则抽取仅作为无模型时的兜底方案。")

    # ── Session state ─────────────────────────────────────────────────────────
    if use_sample or "input_text" not in st.session_state:
        st.session_state.input_text = SAMPLES[sample_name]

    # ── Row 1: text input (left) | metrics + NER (right) ─────────────────────
    left, right = st.columns([0.95, 1.05], gap="large")

    with left:
        st.subheader("📝 文本输入")
        text = st.text_area(
            "输入英文或中文语料",
            key="input_text",
            height=250,
            label_visibility="collapsed",
        )
        extract_clicked = st.button("🔍 抽取信息", type="primary", use_container_width=True)

    # ── Compute ───────────────────────────────────────────────────────────────
    if extract_clicked or "last_text" not in st.session_state:
        st.session_state.last_text = st.session_state.input_text

    current_text = st.session_state.get("last_text", text)
    selected_language = (
        detect_language_option(current_text)
        if language_choice == "自动检测"
        else language_choice
    )
    if backend == "spaCy 模型抽取":
        all_entities, backend_status = extract_entities_spacy(current_text, selected_language)
    else:
        all_entities = extract_entities(current_text)
        backend_status = "已使用规则抽取兜底模式。"

    flat_entities = select_flat_entities(all_entities)
    nested = nested_entities(all_entities)
    relations = extract_relations(current_text, flat_entities, include_related=include_related)
    graph_entities = all_entities if show_nested else flat_entities
    nodes, edges = graph_payload(graph_entities, relations)

    # ── Right column: metrics + NER highlight ────────────────────────────────
    with right:
        metric_cols = st.columns(3)
        metric_cols[0].metric("实体数", len(flat_entities))
        metric_cols[1].metric("关系数", len(relations))
        metric_cols[2].metric("嵌套候选", len(nested))
        st.caption(backend_status)

        st.subheader("🏷️ 实体识别")
        st.markdown(
            """
            <div class="legend">
              <span class="legend-item"><i class="legend-dot" style="--dot:#1a73e8"></i>Person 人物</span>
              <span class="legend-item"><i class="legend-dot" style="--dot:#137333"></i>Organization 组织</span>
              <span class="legend-item"><i class="legend-dot" style="--dot:#f9ab00"></i>Location 地点</span>
              <span class="legend-item"><i class="legend-dot" style="--dot:#7b1fa2"></i>Other 其他</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if show_bio:
            st.dataframe(
                token_bio_rows(current_text, flat_entities),
                use_container_width=True,
                height=292,
            )
        else:
            st.markdown(
                f"<div class='highlight-box'>"
                f"{render_highlighted_text(current_text, flat_entities)}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Nested entity notice (only when there are nested entities) ────────────
    if show_nested and nested:
        st.markdown(
            "<div class='note'>⚠️ 检测到嵌套实体候选。"
            "单层 BIO 会优先保留最长实体，因此内部实体不会同时进入同一条 BIO 序列。</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Row 2: entity table | relation table ──────────────────────────────────
    table_left, table_right = st.columns([0.92, 1.08], gap="large")

    with table_left:
        st.subheader("📋 实体列表")
        st.dataframe(entity_rows(graph_entities, nested), use_container_width=True)

    with table_right:
        st.subheader("🔗 关系抽取")
        rows = relation_rows(relations)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info(
                "未发现可由当前规则识别的关系。"
                "可以尝试包含 founded、headquartered、合作、位于 等触发词。"
            )

    st.divider()

    # ── Row 3: knowledge graph ────────────────────────────────────────────────
    st.subheader("🕸️ 知识图谱")
    render_graph(nodes, edges)


if __name__ == "__main__":
    main()
