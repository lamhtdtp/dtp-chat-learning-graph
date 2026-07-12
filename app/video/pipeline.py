"""Orchestrate sinh 1 video cho khái niệm: answer grounded -> script -> guard ->
render slides -> TTS -> ffmpeg -> storage. Cập nhật trạng thái job theo từng
bước (US-16 Scenario 3). Bất kỳ lỗi nào -> job FAILED + log lý do, KHÔNG phát
hành video hỏng (US-16/US-18 Scenario 4).

Video theo KHÁI NIỆM (không theo câu chữ 1 học sinh): câu trả lời "đại diện"
được sinh lại grounded từ chính khái niệm -> dùng chung + pre-generate được.
"""

import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.grounding import has_grounding
from app.graph.nodes.qa import qa_node
from app.retrieval import retriever
from app.video import animate, scene, storage
from app.video.concept import CONCEPT_MON, CONCEPT_QUERY
from app.video.guard import check_script
from app.video.script import generate_script


class PipelineError(Exception):
    pass


async def _grounded_answer(slug: str) -> tuple[str, str]:
    query = CONCEPT_QUERY.get(slug, slug.replace("_", " "))
    mon = CONCEPT_MON.get(slug, "toan")  # ground từ đúng kho SGK của môn khái niệm
    chunks = await retriever.retrieve(
        query, mon=mon, khoi="lop_6", top_k=5, score_threshold=0.4
    )
    if not has_grounding(chunks):
        raise PipelineError(f"Không đủ ngữ liệu SGK cho khái niệm {slug!r}")
    state = {"messages": [{"role": "user", "content": query}], "retrieved": chunks}
    answer = (await qa_node(state))["answer"]
    sources = "\n\n".join(f"[tr.{c.page_no}] {c.content}" for c in chunks)
    return answer, sources


def _safe_name(concept_key: str) -> str:
    return concept_key.replace("::", "__").replace("/", "_") + ".mp4"


async def build_video_for_job(session: AsyncSession, job) -> "job":
    """Chạy full pipeline cho job (đã QUEUED). Đặt job.status và flush theo bước."""
    from app.video.cache import DONE, FAILED, RENDERING

    job.status = RENDERING
    await session.flush()
    slug = job.concept_key.split("::")[0]
    fallback_title = "Tiếng Anh lớp 6" if CONCEPT_MON.get(slug) == "tieng_anh" else "Toán lớp 6"
    try:
        answer, sources = await _grounded_answer(slug)

        storyboard = await generate_script(answer, sources=sources)
        guard = check_script(storyboard, answer)
        if not guard.ok:
            raise PipelineError(f"Guard chặn kịch bản: {guard.reason}")

        # Ảnh nền cảnh AI (giáo viên + lớp học). Lỗi sinh ảnh -> None -> tự lùi
        # về nền gradient + minh hoạ vector, KHÔNG làm hỏng video.
        try:
            background = await scene.fetch_scene(storyboard.tieu_de or fallback_title)
        except Exception:  # noqa: BLE001
            background = None

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp4"
            # Video câm: nền cảnh AI (hoặc gradient) + bảng nội dung + phụ đề.
            duration = animate.render_storyboard(
                storyboard, out, concept_slug=slug, background=background
            )
            url = storage.save_video(out, _safe_name(job.concept_key))

        job.status = DONE
        job.video_url = url
        job.title = storyboard.tieu_de or None
        job.duration_sec = duration
    except Exception as exc:  # noqa: BLE001 - mọi lỗi -> FAILED, không phát hành video hỏng
        job.status = FAILED
        job.error = str(exc)[:500]
    finally:
        await session.flush()
    return job
