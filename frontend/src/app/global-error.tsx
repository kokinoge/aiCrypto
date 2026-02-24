"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="ja">
      <body>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
          <div style={{ textAlign: "center" }}>
            <h2>エラーが発生しました</h2>
            <button onClick={() => reset()} style={{ marginTop: "1rem", padding: "0.5rem 1rem" }}>
              再試行
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
