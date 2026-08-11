from app.ingestion import celery_app as ca


def test_task_duoc_dang_ky():
    assert "ingest_book" in ca.celery_app.tasks


def test_broker_dung_redis_url():
    # broker phải trỏ Redis (cùng settings) — không dùng broker mặc định
    assert ca.celery_app.conf.broker_url.startswith("redis://")


def test_ingest_task_goi_dung_ham_async(mocker):
    """Chạy eager (task-always-eager) và mock ingest_book để không tốn OCR/API.
    Kiểm task bọc đúng hàm async và truyền tham số xuống."""
    ca.celery_app.conf.task_always_eager = True

    async def fake_ingest(**kwargs):
        fake_ingest.called_with = kwargs
        return 42
    mocker.patch("app.ingestion.tasks.ingest_book", side_effect=fake_ingest)

    result = ca.ingest_book_task.apply(kwargs=dict(tap=1, sach="s1", pages=[5, 6])).get()

    assert result == 42
    assert fake_ingest.called_with["tap"] == 1
    assert fake_ingest.called_with["sach"] == "s1"
    assert fake_ingest.called_with["pages"] == [5, 6]


def test_khong_dung_result_backend():
    """Sự cố prod 2026-08: `.delay()` nổ RuntimeError vì Celery cố SUBSCRIBE vào
    result store trên Redis đang bật mật khẩu — trong khi KHÔNG chỗ nào trong app
    đọc kết quả task (trạng thái video nằm ở bảng video_jobs). Backend chỉ là mặt
    hỏng thừa; giữ nó tắt."""
    assert not ca.celery_app.conf.result_backend
