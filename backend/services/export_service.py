"""
导出服务：生成 Excel 和 PDF 报告
"""
import io
import base64
from pathlib import Path
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter


def _safe(val, default="—"):
    if val is None:
        return default
    if isinstance(val, list):
        return "；".join(str(v) for v in val)
    return str(val)


def _analysis_source_label(analysis: dict) -> str:
    source = analysis.get("analysis_source") or analysis.get("analysis_mode")
    mode = analysis.get("analysis_mode")
    if source == "whole_video" or mode == "whole_video_context":
        return "整片上下文"
    if source == "chunk_segment" or mode == "chunk_segment_context":
        return "分块上下文"
    if source == "merged_context" or mode == "merged_context":
        return "合并上下文"
    if source == "shot_clip" or mode == "shot_clip":
        return "单镜头"
    return _safe(source, "单镜头")


def export_excel(video: dict, shots: List[dict], analysis: dict, segments: dict | None = None) -> bytes:
    wb = Workbook()

    # ── Sheet 1: 镜头分析 ──────────────────────────────
    ws = wb.active
    ws.title = "镜头分析"

    header_fill = PatternFill("solid", fgColor="1F3864")
    alt_fill = PatternFill("solid", fgColor="EEF2FF")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    headers = [
        "缩略图", "镜头#", "时长(s)", "开始", "结束",
        "景别", "运镜", "构图", "光影", "色调",
        "WHAT", "HOW", "WHY",
        "叙事-场景", "叙事-事件", "叙事-信息",
        "情绪功能", "叙事决策", "节奏贡献",
        "台词", "声音类型", "声画关系", "声音叙事作用",
        "分析方式", "合并镜头", "合并段落分析",
        "声音连续", "动作连续",
    ]

    ws.row_dimensions[1].height = 20
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    # 列宽
    col_widths = [12, 6, 8, 8, 8, 8, 8, 20, 18, 15,
                  30, 30, 35, 20, 25, 25, 18, 30, 15,
                  25, 18, 20, 30, 14, 20, 40, 30, 30]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for row_i, shot in enumerate(shots, 2):
        a = shot.get("analysis") or {}
        nl = a.get("narrative_level") or {}
        audio = a.get("audio") or {}
        audio_continuity = a.get("audio_continuity") or {}
        action_continuity = a.get("action_continuity") or {}
        fill = alt_fill if row_i % 2 == 0 else PatternFill()

        ws.row_dimensions[row_i].height = 60

        values = [
            "",  # 缩略图占位
            shot.get("index", row_i - 1) + 1,
            round(shot.get("duration", 0), 1),
            f"{shot.get('start_time', 0):.1f}s",
            f"{shot.get('end_time', 0):.1f}s",
            _safe(a.get("shot_scale")),
            _safe(a.get("camera_movement")),
            _safe(a.get("composition")),
            _safe(a.get("lighting")),
            _safe(a.get("color_tone")),
            _safe(a.get("what")),
            _safe(a.get("how")),
            _safe(a.get("why")),
            _safe(nl.get("scene")),
            _safe(nl.get("event")),
            _safe(nl.get("information")),
            _safe(a.get("emotional_function")),
            _safe(a.get("narrative_decision")),
            _safe(a.get("rhythm_contribution")),
            _safe(audio.get("dialogue")),
            _safe(audio.get("sound_type")),
            _safe(a.get("audiovisual_sync")),
            _safe(a.get("audio_narrative_role")),
            _analysis_source_label(a),
            _safe([i + 1 for i in a.get("analysis_shot_indices", [])]) if a.get("analysis_shot_indices") else "—",
            _safe(a.get("merged_segment_analysis")),
            _safe(audio_continuity.get("notes")),
            _safe(action_continuity.get("notes")),
        ]

        for col_i, val in enumerate(values, 1):
            if col_i == 1:
                continue  # 缩略图单独处理
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = border
            if fill.fill_type:
                cell.fill = fill

        # 插入缩略图
        thumb = shot.get("thumbnail_path")
        if thumb and Path(thumb).exists():
            try:
                img = XLImage(thumb)
                img.height = 56
                img.width = 80
                ws.add_image(img, f"A{row_i}")
            except Exception:
                pass

    # ── Sheet 2: 整体分析 ──────────────────────────────
    ws2 = wb.create_sheet("整体分析")
    ws2.column_dimensions["A"].width = 25
    ws2.column_dimensions["B"].width = 80

    if analysis:
        rows = []
        c = analysis.get("continuity") or {}
        r = analysis.get("rhythm") or {}
        n = analysis.get("narrative_structure") or {}
        g = analysis.get("genre_patterns") or {}

        rows += [
            ("【连贯性】", ""),
            ("景别流动", _safe(c.get("shot_scale_flow"))),
            ("运镜衔接", _safe(c.get("movement_coherence"))),
            ("情绪弧线", _safe(c.get("emotional_arc"))),
            ("色调连续性", _safe(c.get("color_continuity"))),
            ("声音弧线", _safe(c.get("audio_arc"))),
            ("", ""),
            ("【节奏】", ""),
            ("平均镜头时长", f"{r.get('avg_shot_duration', '—')}s"),
            ("最短/最长镜头", f"{r.get('shortest_shot', '—')}s / {r.get('longest_shot', '—')}s"),
            ("剧情变化频率", _safe(r.get("plot_change_frequency"))),
            ("信息密度分布", _safe(r.get("info_density_pattern"))),
            ("节奏评估", _safe(r.get("pacing_assessment"))),
            ("张力高潮点", _safe(r.get("tension_peaks"))),
            ("", ""),
            ("【叙事结构】", ""),
            ("推测类型", _safe(n.get("detected_genre"))),
            ("三幕结构", _safe(n.get("three_act"))),
            ("关键转折点", _safe(n.get("key_turning_points"))),
            ("信息揭示策略", _safe(n.get("information_release_strategy"))),
            ("", ""),
            ("【类型规律】", ""),
            ("类型惯例体现", _safe(g.get("structural_notes"))),
            ("与惯例的偏差", _safe(g.get("deviation_notes"))),
        ]

        header_fill2 = PatternFill("solid", fgColor="2E4057")
        for r_i, (k, v) in enumerate(rows, 1):
            k_cell = ws2.cell(row=r_i, column=1, value=k)
            v_cell = ws2.cell(row=r_i, column=2, value=v)
            k_cell.alignment = Alignment(vertical="top", wrap_text=True)
            v_cell.alignment = Alignment(vertical="top", wrap_text=True)
            if k.startswith("【"):
                k_cell.font = Font(bold=True, color="FFFFFF")
                v_cell.font = Font(bold=True, color="FFFFFF")
                k_cell.fill = header_fill2
                v_cell.fill = header_fill2
            ws2.row_dimensions[r_i].height = max(15, min(120, len(str(v)) // 2))

    segment_rows = (segments or {}).get("segments") or []
    if segment_rows:
        ws3 = wb.create_sheet("段落分析")
        segment_headers = ["段落#", "镜头", "类型", "标题", "摘要", "合并原因", "声音连续", "动作连续", "剪辑逻辑", "情绪推进", "叙事功能"]
        widths = [8, 18, 18, 24, 50, 50, 36, 36, 40, 36, 40]
        for col, (header, width) in enumerate(zip(segment_headers, widths), 1):
            cell = ws3.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
            ws3.column_dimensions[get_column_letter(col)].width = width
        for row_i, segment in enumerate(segment_rows, 2):
            indices = [int(i) + 1 for i in segment.get("shot_indices", [])]
            values = [
                segment.get("segment_index", row_i - 2) + 1,
                _safe(indices),
                _safe(segment.get("segment_type")),
                _safe(segment.get("title")),
                _safe(segment.get("summary")),
                _safe(segment.get("merge_reason")),
                _safe(segment.get("audio_continuity")),
                _safe(segment.get("action_continuity")),
                _safe(segment.get("editing_logic")),
                _safe(segment.get("emotional_arc")),
                _safe(segment.get("narrative_function")),
            ]
            ws3.row_dimensions[row_i].height = 72
            for col_i, val in enumerate(values, 1):
                cell = ws3.cell(row=row_i, column=col_i, value=val)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border
                if row_i % 2 == 0:
                    cell.fill = alt_fill

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_pdf_html(video: dict, shots: List[dict], analysis: dict, segments: dict | None = None) -> str:
    """生成 HTML 字符串，由 WeasyPrint 转 PDF"""

    def thumb_b64(path):
        if path and Path(path).exists():
            with open(path, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        return ""

    shot_cards = ""
    for shot in shots:
        a = shot.get("analysis") or {}
        nl = a.get("narrative_level") or {}
        audio = a.get("audio") or {}
        thumb = thumb_b64(shot.get("thumbnail_path"))
        img_tag = f'<img src="{thumb}" class="thumb">' if thumb else '<div class="no-thumb">无缩略图</div>'

        shot_cards += f"""
<div class="shot-card">
  <div class="shot-header">
    <div class="thumb-cell">{img_tag}</div>
    <div class="shot-meta">
      <h3>镜头 #{shot.get('index',0)+1}</h3>
      <p>时长：{shot.get('duration',0):.1f}s &nbsp;|&nbsp;
         {shot.get('start_time',0):.1f}s → {shot.get('end_time',0):.1f}s</p>
      <p><b>景别：</b>{_safe(a.get('shot_scale'))} &nbsp;
         <b>运镜：</b>{_safe(a.get('camera_movement'))}</p>
      <p><b>光影：</b>{_safe(a.get('lighting'))}</p>
      <p><b>色调：</b>{_safe(a.get('color_tone'))}</p>
      {f"<p><b>分析方式：</b>{_analysis_source_label(a)} &nbsp; <b>合并镜头：</b>{_safe([i + 1 for i in a.get('analysis_shot_indices', [])])}</p>" if a.get('analysis_mode') == 'merged_context' else f"<p><b>分析方式：</b>{_analysis_source_label(a)}</p>"}
    </div>
  </div>
  <div class="analysis-body">
    <div class="why-block">
      <div class="label">WHAT</div><div class="content">{_safe(a.get('what'))}</div>
      <div class="label">HOW</div><div class="content">{_safe(a.get('how'))}</div>
      <div class="label">WHY</div><div class="content why-text">{_safe(a.get('why'))}</div>
    </div>
    <div class="narrative-block">
      <b>叙事层级</b>
      <p>场景：{_safe(nl.get('scene'))}</p>
      <p>事件：{_safe(nl.get('event'))}</p>
      <p>信息：{_safe(nl.get('information'))}</p>
    </div>
    <div class="narrative-block">
      <b>声音</b>
      <p>台词：{_safe(audio.get('dialogue'))}</p>
      <p>声音类型：{_safe(audio.get('sound_type'))}</p>
      <p>声画关系：{_safe(a.get('audiovisual_sync'))}</p>
      <p>声音叙事：{_safe(a.get('audio_narrative_role'))}</p>
    </div>
    <p><b>情绪功能：</b>{_safe(a.get('emotional_function'))}</p>
    <p><b>叙事决策：</b>{_safe(a.get('narrative_decision'))}</p>
    <p><b>节奏贡献：</b>{_safe(a.get('rhythm_contribution'))}</p>
  </div>
</div>"""

    segments_html = ""
    segment_rows = (segments or {}).get("segments") or []
    if segment_rows:
        cards = ""
        for segment in segment_rows:
            cards += f"""
  <div class="segment-card">
    <h3>{_safe(segment.get('title'), '段落')}</h3>
    <p><b>镜头：</b>{_safe([int(i) + 1 for i in segment.get('shot_indices', [])])} &nbsp; <b>类型：</b>{_safe(segment.get('segment_type'))}</p>
    <p><b>摘要：</b>{_safe(segment.get('summary'))}</p>
    <p><b>合并原因：</b>{_safe(segment.get('merge_reason'))}</p>
    <p><b>声音连续：</b>{_safe(segment.get('audio_continuity'))}</p>
    <p><b>动作连续：</b>{_safe(segment.get('action_continuity'))}</p>
    <p><b>剪辑逻辑：</b>{_safe(segment.get('editing_logic'))}</p>
    <p><b>情绪推进：</b>{_safe(segment.get('emotional_arc'))}</p>
    <p><b>叙事功能：</b>{_safe(segment.get('narrative_function'))}</p>
  </div>"""
        segments_html = f"""
<div class="section">
  <h2>段落分析</h2>
  <p style="color:#6b7280;margin-bottom:10px">来源：{_safe((segments or {}).get('strategy'))}；{_safe((segments or {}).get('reason'))}</p>
  {cards}
</div>"""

    overall_html = ""
    if analysis:
        c = analysis.get("continuity") or {}
        r = analysis.get("rhythm") or {}
        n = analysis.get("narrative_structure") or {}
        overall_html = f"""
<div class="section">
  <h2>整体分析</h2>
  <h3>连贯性</h3>
  <p><b>景别流动：</b>{_safe(c.get('shot_scale_flow'))}</p>
  <p><b>运镜衔接：</b>{_safe(c.get('movement_coherence'))}</p>
  <p><b>情绪弧线：</b>{_safe(c.get('emotional_arc'))}</p>
  <p><b>色调连续：</b>{_safe(c.get('color_continuity'))}</p>
  <p><b>声音弧线：</b>{_safe(c.get('audio_arc'))}</p>
  <h3>节奏</h3>
  <p><b>平均镜头时长：</b>{r.get('avg_shot_duration','—')}s</p>
  <p><b>节奏评估：</b>{_safe(r.get('pacing_assessment'))}</p>
  <p><b>信息密度：</b>{_safe(r.get('info_density_pattern'))}</p>
  <h3>叙事结构</h3>
  <p><b>推测类型：</b>{_safe(n.get('detected_genre'))}</p>
  <p><b>三幕结构：</b>{_safe(n.get('three_act'))}</p>
  <p><b>信息揭示策略：</b>{_safe(n.get('information_release_strategy'))}</p>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'WenQuanYi Zen Hei', 'DejaVu Sans', sans-serif; font-size: 11px;
          color: #1a1a2e; background: #f8f9ff; }}
  h1 {{ font-size: 20px; color: #1F3864; border-bottom: 3px solid #4f46e5;
        padding-bottom: 8px; margin-bottom: 16px; }}
  h2 {{ font-size: 16px; color: #312e81; margin: 20px 0 10px; }}
  h3 {{ font-size: 13px; color: #4338ca; margin: 12px 0 6px; }}
  .shot-card {{ background: white; border-radius: 8px; padding: 12px;
                margin-bottom: 16px; break-inside: avoid;
                border-left: 4px solid #4f46e5; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .shot-header {{ display: table; width: 100%; table-layout: fixed; margin-bottom: 10px; }}
  .thumb-cell {{ display: table-cell; width: 132px; padding-right: 12px; vertical-align: top; }}
  .shot-meta {{ display: table-cell; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
  .thumb {{ display: block; width: 120px; height: 68px; object-fit: cover; border-radius: 4px; }}
  .no-thumb {{ width: 120px; height: 68px; background: #e5e7eb; border-radius: 4px;
               display: block; line-height: 68px; text-align: center; color: #9ca3af; }}
  .shot-meta h3 {{ font-size: 14px; color: #1e1b4b; margin: 0 0 4px; }}
  .shot-meta p {{ margin: 2px 0; color: #374151; line-height: 1.55; }}
  .analysis-body {{ border-top: 1px solid #e5e7eb; padding-top: 8px; }}
  .why-block {{ background: #f5f3ff; border-radius: 6px; padding: 8px; margin: 8px 0; }}
  .label {{ font-weight: bold; color: #4f46e5; font-size: 10px;
            text-transform: uppercase; margin-top: 6px; }}
  .why-text {{ color: #1e1b4b; font-style: italic; }}
  .content {{ color: #374151; margin-bottom: 4px; overflow-wrap: anywhere; word-break: break-word; }}
  .narrative-block {{ background: #f0fdf4; border-radius: 6px; padding: 8px; margin: 6px 0; }}
  .narrative-block b {{ color: #166534; }}
  .section {{ background: white; border-radius: 8px; padding: 16px; margin-top: 20px; }}
  .segment-card {{ break-inside: avoid; border: 1px solid #e5e7eb; border-left: 4px solid #0ea5e9; border-radius: 8px; padding: 10px; margin: 10px 0; background: #f8fbff; }}
  p {{ margin: 3px 0; line-height: 1.5; }}
</style>
</head>
<body>
<h1>拉片报告 — {video.get('filename','')}</h1>
<p style="color:#6b7280;margin-bottom:20px">
  时长：{video.get('duration',0):.1f}s &nbsp;|&nbsp; 共 {len(shots)} 个镜头
</p>
{shot_cards}
{segments_html}
{overall_html}
</body>
</html>"""
