import { useState } from "react";
import { getItestQuiz } from "../api";
import type { ItestOffer, QuizData } from "../types";
import { QuizModal } from "./QuizModal";

// Mời học sinh luyện tập bằng bài trắc nghiệm i-Test cho chủ đề vừa hỏi. Bấm nút
// -> tải đề THẬT (query i-Test trực tiếp, như repo dtp-chat-learning) -> mở
// QuizModal tương tác. Không tải sẵn (tránh chờ nếu học sinh không cần).
export function ItestBlock({ offer }: { offer: ItestOffer }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [data, setData] = useState<QuizData | undefined>();

  const load = async () => {
    setOpen(true);
    setLoading(true);
    setError(undefined);
    try {
      setData(await getItestQuiz(offer.topic));
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Chưa tạo được bài trắc nghiệm");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="itest-block">
        <button className="itest-toggle" type="button" onClick={load}>
          📝 Luyện tập với i-Test
        </button>
      </div>
      {open && (
        <QuizModal
          loading={loading}
          error={error}
          data={data}
          onClose={() => setOpen(false)}
          onRetry={load}
        />
      )}
    </>
  );
}
