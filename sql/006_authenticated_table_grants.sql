-- The workspace API acts as the signed-in user, but these tables had no
-- table-level privileges for `authenticated`, so every read/write failed with
-- "permission denied" before RLS was even evaluated. RLS (sql/003) still
-- decides which rows each user can see or change.
grant select, insert, update, delete on
  public.documents,
  public.document_analyses,
  public.property_facts,
  public.fact_provenance,
  public.property_evidence,
  public.property_issues,
  public.property_knowledge_links,
  public.ai_feedback,
  public.document_intelligence_results,
  public.ai_analysis_logs
to authenticated;
