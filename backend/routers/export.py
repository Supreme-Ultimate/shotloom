from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db, Shot, VideoAnalysis, User
from services.export_service import export_excel, export_pdf_html
from logger import app_logger
from auth import get_current_user
from permissions import get_video_for_user
from services.analysis_config import get_or_create_video_config
from config import VISION_MODEL_NAME, ASR_MODEL_NAME

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export/{video_id}")
def export_report(
    video_id: int,
    format: str = Query("excel", pattern="^(excel|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        app_logger.info(f"开始导出: video_id={video_id}, format={format}")

        video = get_video_for_user(video_id, current_user, db)

        shots = db.query(Shot).filter(Shot.video_id == video_id).order_by(Shot.index).all()
        va = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
        config_row = get_or_create_video_config(video_id, db)
        has_results = any(s.analysis for s in shots) or va is not None
        schema = config_row.active_snapshot if has_results else config_row.draft_config

        video_dict = {
            "id": video.id,
            "filename": video.filename,
            "duration": video.duration,
            "vision_model": VISION_MODEL_NAME,
            "asr_model": ASR_MODEL_NAME,
        }
        shots_list = [
            {
                "index": s.index,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration": s.duration,
                "thumbnail_path": s.thumbnail_path,
                "analysis": s.analysis,
            }
            for s in shots
        ]
        analysis_dict = va.continuity_report if va else {}
        segments_dict = va.segments_report if va else {}

        name = video.filename.rsplit(".", 1)[0]

        # 使用 URL 编码处理中文文件名
        from urllib.parse import quote

        if format == "excel":
            app_logger.info("生成 Excel 文件")
            data = export_excel(video_dict, shots_list, analysis_dict, segments_dict, schema)
            app_logger.info(f"Excel 生成成功，大小: {len(data)} bytes")
            encoded_filename = quote(f"{name}_拉片报告.xlsx")
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
            )
        else:
            try:
                from weasyprint import HTML
            except ImportError:
                raise HTTPException(500, "WeasyPrint 未安装，请运行: pip install weasyprint")
            app_logger.info("生成 PDF 文件")
            html_str = export_pdf_html(video_dict, shots_list, analysis_dict, segments_dict, schema)
            pdf_bytes = HTML(string=html_str).write_pdf()
            app_logger.info(f"PDF 生成成功，大小: {len(pdf_bytes)} bytes")
            encoded_filename = quote(f"{name}_拉片报告.pdf")
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
            )
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"导出失败: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(500, f"导出失败: {str(e)}")
