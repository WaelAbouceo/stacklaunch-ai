import { useApp } from "../../store/AppContext";

export default function KnowledgeBaseTab() {
  const { project } = useApp();
  if (!project) return null;
  const kb = project.knowledgeBase;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Knowledge Base</h1>
          <div className="desc">
            {kb.pagesIndexed} pages crawled and indexed from {project.websiteUrl}. Used for grounded
            RAG answers about the company.
          </div>
        </div>
        <span className="badge green dot">Indexed</span>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {kb.pages.map((p) => (
          <div className="card" key={p.url} style={{ padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>📄</span>
              <strong style={{ fontSize: 15 }}>{p.title}</strong>
              <span className="badge" style={{ marginLeft: "auto" }}>
                indexed
              </span>
            </div>
            <a className="mono" style={{ fontSize: 12, wordBreak: "break-all" }} href={p.url}>
              {p.url}
            </a>
            <p className="muted" style={{ fontSize: 13.5, margin: "8px 0 10px" }}>
              {p.summary}
            </p>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {p.topics.map((t) => (
                <span key={t} className="perm-tag">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
