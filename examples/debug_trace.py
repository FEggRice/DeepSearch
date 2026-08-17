"""
Debug Trace — 全数据流可视化测试脚本
=======================================
在控制台中逐步骤展示 DeepSearchAgent 的完整内部数据流动，
包括：LLM 输入/输出、Node 调用链、State 变化、搜索过程。

用法：
    cd DeepSearchAgent-Demo
    python examples/debug_trace.py

首次运行会提示输入课题，也可以直接命令行传参：
    python examples/debug_trace.py "量子计算最新进展"
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llms import DeepSeekLLM, OpenAILLM
from src.nodes import (
    ReportStructureNode,
    FirstSearchNode,
    ReflectionNode,
    FirstSummaryNode,
    ReflectionSummaryNode,
    ReportFormattingNode,
)
from src.prompts import (
    SYSTEM_PROMPT_REPORT_STRUCTURE,
    SYSTEM_PROMPT_FIRST_SEARCH,
    SYSTEM_PROMPT_FIRST_SUMMARY,
    SYSTEM_PROMPT_REFLECTION,
    SYSTEM_PROMPT_REFLECTION_SUMMARY,
    SYSTEM_PROMPT_REPORT_FORMATTING,
)
from src.state import State
from src.tools import tavily_search
from src.utils import Config, load_config, format_search_results_for_prompt

# ─── 终端彩色输出辅助 ───
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
BG_BLUE = "\033[44m"
BG_GREEN = "\033[42m"


def banner(title: str):
    print(f"\n{BG_BLUE}{BOLD}  {title}  {RESET}\n")


def section(title: str):
    print(f"\n{CYAN}{'─'*70}{RESET}")
    print(f"{CYAN}│ {BOLD}{title}{RESET}")
    print(f"{CYAN}{'─'*70}{RESET}")


def sub_step(label: str):
    print(f"\n  {GREEN}▸ {label}{RESET}")


def kv(key: str, value: Any, max_len: int = 500):
    """打印键值对，自动截断长内容"""
    val_str = str(value)
    if isinstance(value, str) and len(val_str) > max_len:
        val_str = val_str[:max_len] + f"{YELLOW} ... [截断，共 {len(value)} 字符]{RESET}"
    print(f"    {DIM}{key}:{RESET} {val_str}")


def kv_json(key: str, obj: Any):
    """打印 JSON 对象"""
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    print(f"    {DIM}{key}:{RESET}")
    for line in s.split("\n"):
        print(f"      {line}")


def diff_state(state: State, prev_paragraphs_count: int, prev_summaries: List[str], action: str):
    """对比 State 变化"""
    now_count = len(state.paragraphs)
    if now_count != prev_paragraphs_count:
        print(f"    {MAGENTA}  paragraphs 数量变化: {prev_paragraphs_count} → {now_count}{RESET}")

    for i, p in enumerate(state.paragraphs):
        if i < len(prev_summaries):
            old = prev_summaries[i]
            new = p.research.latest_summary
            if old != new and new:
                print(f"    {MAGENTA}  paragraphs[{i}].research.latest_summary 已更新{RESET}")
                print(f"    {MAGENTA}  旧长度: {len(old)} 字符 → 新长度: {len(new)} 字符{RESET}")
                print(f"    {MAGENTA}  新增内容预览: {new[len(old):len(old)+200]}...{RESET}")


def snapshot_summaries(state: State) -> List[str]:
    return [p.research.latest_summary for p in state.paragraphs]


# ════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════

def main():
    # ── 0. 获取课题 ──
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input(f"{BOLD}🔍 请输入研究课题: {RESET}").strip()
        if not query:
            query = "2025年人工智能发展趋势"
            print(f"{DIM}  使用默认课题: {query}{RESET}")

    banner(f"DeepSearchAgent 全数据流追踪")
    print(f"  课题: {BOLD}{query}{RESET}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 1. 加载配置 ──
    section("阶段 0: 加载配置 & 初始化 Agent")
    try:
        config = load_config()
    except Exception:
        print(f"  {YELLOW}⚠ config.py 未找到或 API Key 未设置，尝试从环境变量加载...{RESET}")
        config = Config.from_file(os.path.join(os.path.dirname(__file__), '..', 'config.py'))

    print(f"  LLM 提供商 : {config.default_llm_provider}")
    print(f"  模型        : {config.deepseek_model if config.default_llm_provider == 'deepseek' else config.openai_model}")
    print(f"  反思轮次    : {config.max_reflections}")
    print(f"  每次搜索条数: {config.max_search_results}")
    print(f"  内容截断长度: {config.max_content_length}")

    # ── 2. 初始化 LLM ──
    sub_step("初始化 LLM 客户端")
    if config.default_llm_provider == "deepseek":
        llm_client = DeepSeekLLM(api_key=config.deepseek_api_key, model_name=config.deepseek_model)
    else:
        llm_client = OpenAILLM(api_key=config.openai_api_key, model_name=config.openai_model)
    print(f"    类型: {type(llm_client).__name__}")
    kv("info", llm_client.get_model_info())

    # ── 3. 初始化节点 ──
    sub_step("初始化 5 个处理节点")
    first_search_node = FirstSearchNode(llm_client)
    reflection_node = ReflectionNode(llm_client)
    first_summary_node = FirstSummaryNode(llm_client)
    reflection_summary_node = ReflectionSummaryNode(llm_client)
    report_formatting_node = ReportFormattingNode(llm_client)
    print(f"    {DIM}FirstSearchNode, ReflectionNode, FirstSummaryNode, ReflectionSummaryNode, ReportFormattingNode 已创建{RESET}")
    print(f"    {DIM}全部注入了同一个 llm_client 实例{RESET}")

    # ── 4. 初始化 State ──
    state = State()
    kv("state", f"State() — query='', paragraphs=[], is_completed=False")

    # ════════════════════════════════════════════════════════════
    # 阶段 1: 生成报告结构
    # ════════════════════════════════════════════════════════════
    section("阶段 1: ReportStructureNode — 生成报告大纲")

    sub_step("创建 ReportStructureNode")
    rs_node = ReportStructureNode(llm_client, query)
    print(f"    节点类型: {type(rs_node).__name__}")
    kv("输入", rs_node.query)

    sub_step("调 LLM 生成大纲 (invoke)")
    print(f"    {DIM}System Prompt: SYSTEM_PROMPT_REPORT_STRUCTURE (实际导入){RESET}")
    print(f"    {DIM}User Prompt  : \"{query}\"{RESET}")

    try:
        rs_raw = llm_client.invoke(SYSTEM_PROMPT_REPORT_STRUCTURE, query)
    except Exception as e:
        print(f"    {RED}✗ LLM 调用失败: {e}{RESET}")
        return

    print(f"\n    {GREEN}LLM 原始返回 (前 800 字符):{RESET}")
    print(f"    {YELLOW}{rs_raw[:800]}...{RESET}" if len(rs_raw) > 800 else f"    {YELLOW}{rs_raw}{RESET}")

    # 用 ReportStructureNode 的 process_output（自带容错和降级）
    # 但先做一层解包：LLM 有时会把数组包在 {"type":"array","items":[...]} 里
    try:
        from src.utils.text_processing import remove_reasoning_from_output, clean_json_tags
        cleaned = clean_json_tags(remove_reasoning_from_output(rs_raw))
        parsed = json.loads(cleaned)
        # 解包：如果是 dict 且有 items 字段，提取 items
        if isinstance(parsed, dict) and "items" in parsed and isinstance(parsed["items"], list):
            print(f"    {YELLOW}⚠ 检测到 LLM 把结果包在 Schema 壳里，自动解包 items 字段{RESET}")
            parsed = parsed["items"]
        report_structure = parsed
    except (json.JSONDecodeError, Exception):
        report_structure = rs_raw  # 交给 process_output 处理

    # 如果上面解析出来的不是 list，再走 Node 的标准流程
    if not isinstance(report_structure, list):
        try:
            report_structure = rs_node.process_output(rs_raw)
        except Exception:
            pass

    # 最终降级
    if not isinstance(report_structure, list) or len(report_structure) == 0:
        print(f"    {YELLOW}⚠ 所有解析路径均失败，使用降级大纲{RESET}")
        report_structure = [{"title": "概述", "content": f"对'{query}'的总体概述"},
                            {"title": "详细分析", "content": f"深入分析'{query}'的相关内容"}]

    print(f"\n    {GREEN}解析后的大纲结构:{RESET}")
    kv_json("report_structure", report_structure)

    sub_step("mutate_state: 写入 State.paragraphs")
    print(f"    {DIM}State 变化前: paragraphs = [] (空列表){RESET}")
    state.query = query
    state.report_title = f"关于'{query}'的深度研究报告"
    for i, p in enumerate(report_structure):
        state.add_paragraph(title=p.get("title", f"段落{i+1}"), content=p.get("content", ""))
    print(f"    {DIM}State 变化后: paragraphs = [Paragraph × {len(state.paragraphs)}]{RESET}")
    for i, p in enumerate(state.paragraphs):
        print(f"    {MAGENTA}  paragraphs[{i}]:{RESET}")
        print(f"    {MAGENTA}    title   = \"{p.title}\"{RESET}")
        print(f"    {MAGENTA}    content = \"{p.content}\"{RESET}")
        print(f"    {MAGENTA}    order   = {p.order}{RESET}")

    prev_summaries = snapshot_summaries(state)

    # ════════════════════════════════════════════════════════════
    # 阶段 2: 处理每个段落
    # ════════════════════════════════════════════════════════════
    section(f"阶段 2: 处理段落 (共 {len(state.paragraphs)} 个)")

    for p_idx in range(len(state.paragraphs)):
        paragraph = state.paragraphs[p_idx]
        banner(f"段落 {p_idx + 1}/{len(state.paragraphs)}: 「{paragraph.title}」")

        # ── 2A: 初始搜索 ──
        section(f"  >> 子阶段 2A: FirstSearchNode — 生成初始搜索词")

        search_input = {"title": paragraph.title, "content": paragraph.content}
        print(f"    {DIM}输入数据:{RESET}")
        kv_json("search_input", search_input)

        print(f"\n    {DIM}调 LLM (SYSTEM_PROMPT_FIRST_SEARCH)...{RESET}")
        try:
            search_output = first_search_node.run(search_input)
        except Exception as e:
            print(f"    {RED}✗ FirstSearchNode.run() 失败: {e}{RESET}")
            continue
        search_query = search_output["search_query"]
        reasoning = search_output["reasoning"]

        print(f"\n    {GREEN}FirstSearchNode 返回:{RESET}")
        kv("search_query", search_query)
        kv("reasoning", reasoning)

        print(f"\n    {DIM}调 Tavily 搜索...{RESET}")
        search_results = tavily_search(search_query, max_results=config.max_search_results, timeout=config.search_timeout, api_key=config.tavily_api_key)
        print(f"    {GREEN}搜索结果: {len(search_results)} 条{RESET}")
        for j, r in enumerate(search_results):
            print(f"    {MAGENTA}  [{j+1}] {r.get('title', 'N/A')}{RESET}")
            print(f"    {MAGENTA}      URL  : {r.get('url', 'N/A')}{RESET}")
            print(f"    {MAGENTA}      长度 : {len(r.get('content', ''))} 字符  |  评分: {r.get('score', 'N/A')}{RESET}")

        # ── 写入 State ──
        paragraph.research.add_search_results(search_query, search_results)
        print(f"\n    {DIM}→ State 更新: paragraph.research.search_history 新增 {len(search_results)} 条 Search 记录{RESET}")

        # ── 2B: 初始总结 ──
        section(f"  >> 子阶段 2B: FirstSummaryNode — 生成段落初稿")

        truncated = format_search_results_for_prompt(search_results, config.max_content_length)
        summary_input = {
            "title": paragraph.title,
            "content": paragraph.content,
            "search_query": search_query,
            "search_results": truncated,
        }
        print(f"    {DIM}输入数据:{RESET}")
        kv("title", summary_input["title"])
        kv("content", summary_input["content"])
        kv("search_query", summary_input["search_query"])
        kv("search_results", f"[{len(truncated)} 条截断后的文本，各 ≤ {config.max_content_length} 字符]")
        for j, t in enumerate(truncated):
            preview = t[:200] + "..." if len(t) > 200 else t
            print(f"      {DIM}[{j+1}] 截断后({len(t)}字符): {preview}{RESET}")

        print(f"\n    {DIM}调 LLM (SYSTEM_PROMPT_FIRST_SUMMARY)...{RESET}")
        old_summary = paragraph.research.latest_summary
        try:
            state = first_summary_node.mutate_state(summary_input, state, p_idx)
        except Exception as e:
            print(f"    {RED}✗ FirstSummaryNode.mutate_state() 失败: {e}{RESET}")
            continue

        new_summary = paragraph.research.latest_summary
        print(f"\n    {GREEN}FirstSummaryNode 返回的 latest_summary:{RESET}")
        kv("长度", f"{len(new_summary)} 字符")
        kv("内容 (前500字符)", new_summary[:500])
        print(f"\n    {DIM}→ State 更新: paragraphs[{p_idx}].research.latest_summary{RESET}")
        print(f"    {DIM}  旧值: \"{old_summary[:80]}...\" (如有){RESET}" if old_summary else f"    {DIM}  旧值: (空){RESET}")
        print(f"    {DIM}  新值: \"{new_summary[:80]}...\"{RESET}")

        # ── 2C: 反思循环 ──
        section(f"  >> 子阶段 2C: Reflection Loop (最多 {config.max_reflections} 轮)")

        for ref_i in range(config.max_reflections):
            banner(f"    反思第 {ref_i + 1} 轮")

            # ── ReflectionNode ──
            reflection_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "paragraph_latest_state": paragraph.research.latest_summary,
            }
            print(f"    {DIM}ReflectionNode 输入:{RESET}")
            kv("title", reflection_input["title"])
            kv("content", reflection_input["content"])
            kv("paragraph_latest_state", f"({len(reflection_input['paragraph_latest_state'])} 字符) " + reflection_input["paragraph_latest_state"][:150] + "...")

            print(f"\n    {DIM}调 LLM (SYSTEM_PROMPT_REFLECTION)...{RESET}")
            try:
                reflection_output = reflection_node.run(reflection_input)
            except Exception as e:
                print(f"    {RED}✗ ReflectionNode.run() 失败: {e}{RESET}")
                continue
            ref_query = reflection_output["search_query"]
            ref_reasoning = reflection_output["reasoning"]

            print(f"\n    {GREEN}ReflectionNode 返回:{RESET}")
            kv("search_query", ref_query)
            kv("reasoning", ref_reasoning)

            print(f"\n    {DIM}调 Tavily 搜索...{RESET}")
            ref_results = tavily_search(ref_query, max_results=config.max_search_results, timeout=config.search_timeout, api_key=config.tavily_api_key)
            print(f"    {GREEN}搜索结果: {len(ref_results)} 条{RESET}")
            for j, r in enumerate(ref_results):
                print(f"    {MAGENTA}  [{j+1}] {r.get('title', 'N/A')[:60]}{RESET}")
                print(f"    {MAGENTA}       评分: {r.get('score', 'N/A')}  |  长度: {len(r.get('content', ''))} 字符{RESET}")

            paragraph.research.add_search_results(ref_query, ref_results)
            print(f"\n    {DIM}→ State 更新: search_history 新增 {len(ref_results)} 条{RESET}")

            # ── ReflectionSummaryNode ──
            ref_truncated = format_search_results_for_prompt(ref_results, config.max_content_length)
            ref_summary_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "search_query": ref_query,
                "search_results": ref_truncated,
                "paragraph_latest_state": paragraph.research.latest_summary,
            }
            print(f"\n    {DIM}ReflectionSummaryNode 输入:{RESET}")
            kv("title", ref_summary_input["title"])
            kv("search_query", ref_summary_input["search_query"])
            kv("search_results", f"[{len(ref_truncated)} 条]")
            kv("paragraph_latest_state (旧)", f"({len(ref_summary_input['paragraph_latest_state'])} 字符)")

            print(f"\n    {DIM}调 LLM (SYSTEM_PROMPT_REFLECTION_SUMMARY)...{RESET}")
            old_summary = paragraph.research.latest_summary
            try:
                state = reflection_summary_node.mutate_state(ref_summary_input, state, p_idx)
            except Exception as e:
                print(f"    {RED}✗ ReflectionSummaryNode.mutate_state() 失败: {e}{RESET}")
                continue

            new_summary = paragraph.research.latest_summary
            print(f"\n    {GREEN}ReflectionSummaryNode 返回的 latest_summary:{RESET}")
            kv("长度", f"{len(new_summary)} 字符 (旧: {len(old_summary)} 字符)")

            # 显示新增内容
            if len(new_summary) > len(old_summary):
                added = new_summary[len(old_summary):]
                print(f"    {GREEN}新增内容 ({len(added)} 字符):{RESET}")
                print(f"    {YELLOW}\"{added[:300]}...\"{RESET}" if len(added) > 300 else f"    {YELLOW}\"{added}\"{RESET}")
            else:
                print(f"    {YELLOW}  (内容被重写而非追加，长度变化: {len(old_summary)} → {len(new_summary)}){RESET}")

            print(f"\n    {DIM}→ State 更新: paragraphs[{p_idx}].research.latest_summary 已覆盖{RESET}")
            print(f"    {DIM}→ State 更新: reflection_iteration = {paragraph.research.reflection_iteration}{RESET}")

        # ── 标记段落完成 ──
        paragraph.research.mark_completed()
        search_count = paragraph.research.get_search_count()
        print(f"\n  {GREEN}✓ 段落「{paragraph.title}」处理完成{RESET}")
        print(f"    总搜索次数: {search_count}  反思轮次: {paragraph.research.reflection_iteration}")
        print(f"    最终 latest_summary 长度: {len(paragraph.research.latest_summary)} 字符")

    # ════════════════════════════════════════════════════════════
    # 阶段 3: 最终报告
    # ════════════════════════════════════════════════════════════
    section("阶段 3: ReportFormattingNode — 生成最终报告")

    report_data = []
    for i, p in enumerate(state.paragraphs):
        report_data.append({
            "title": p.title,
            "paragraph_latest_state": p.research.latest_summary,
        })
        print(f"  paragraphs[{i}]: title=\"{p.title}\", latest_summary 长度={len(p.research.latest_summary)}")

    print(f"\n  {DIM}调 LLM (SYSTEM_PROMPT_REPORT_FORMATTING)...{RESET}")
    try:
        final_report = report_formatting_node.run(report_data)
        print(f"  {GREEN}LLM 格式化成功{RESET}")
    except Exception as e:
        print(f"  {YELLOW}LLM 格式化失败: {e}{RESET}")
        print(f"  {YELLOW}启用降级方案: format_report_manually(){RESET}")
        final_report = report_formatting_node.format_report_manually(report_data, state.report_title)

    state.final_report = final_report
    state.mark_completed()

    print(f"\n  {GREEN}最终报告已生成，总长度: {len(final_report)} 字符{RESET}")

    # ── 保存 ──
    output_dir = config.output_dir
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query_safe = "".join(c for c in query if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')[:30]

    report_path = os.path.join(output_dir, f"debug_report_{query_safe}_{timestamp}.md")
    state_path = os.path.join(output_dir, f"debug_state_{query_safe}_{timestamp}.json")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(final_report)
    state.save_to_file(state_path)

    print(f"\n  📄 报告: {report_path}")
    print(f"  📊 State: {state_path}")

    # ════════════════════════════════════════════════════════════
    # 阶段 4: 全局 State 摘要
    # ════════════════════════════════════════════════════════════
    section("阶段 4: 全局 State 摘要")

    progress = state.get_progress_summary()
    kv("query", state.query)
    kv("report_title", state.report_title)
    kv("paragraphs 总数", progress["total_paragraphs"])
    kv("已完成段落", progress["completed_paragraphs"])
    kv("完成度", f"{progress['progress_percentage']:.1f}%")
    kv("is_completed", state.is_completed)
    kv("final_report 长度", f"{len(state.final_report)} 字符")

    print(f"\n  {DIM}每个段落的搜索统计:{RESET}")
    for i, p in enumerate(state.paragraphs):
        print(f"    [{i}] 「{p.title}」— 搜索 {p.research.get_search_count()} 次, 反思 {p.research.reflection_iteration} 轮, 最终 {len(p.research.latest_summary)} 字符")

    banner("追踪完成 ✓")
    print(f"  完整 State JSON 已保存至: {state_path}")
    print(f"  可打开此文件查看全部搜索历史和各版本总结\n")


if __name__ == "__main__":
    main()
