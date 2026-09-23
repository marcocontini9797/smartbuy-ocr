-- SmartBuy feedback persistence for account-owned properties.
CREATE TABLE IF NOT EXISTS smartbuy_feedback_events (
  feedback_event_id UUID PRIMARY KEY,
  property_id BIGINT NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  actor_user_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  expected_version TEXT NOT NULL,
  action TEXT NOT NULL,
  origin TEXT NOT NULL,
  original_payload JSONB NOT NULL,
  corrected_payload JSONB,
  evidence_ids JSONB NOT NULL DEFAULT '[]',
  document_id TEXT,
  analysis_result_id TEXT,
  rag_run_id TEXT,
  failure_stage TEXT NOT NULL,
  component_versions JSONB NOT NULL DEFAULT '{}',
  reason TEXT,
  idempotency_key TEXT NOT NULL,
  command_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS smartbuy_feedback_signals (
  signal_id TEXT PRIMARY KEY,
  feedback_event_id UUID NOT NULL REFERENCES smartbuy_feedback_events(feedback_event_id) ON DELETE CASCADE,
  property_id BIGINT NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  actor_role TEXT NOT NULL,
  payload JSONB NOT NULL,
  expected_payload JSONB,
  evidence_ids JSONB NOT NULL DEFAULT '[]',
  document_id TEXT,
  analysis_result_id TEXT,
  rag_run_id TEXT,
  component_versions JSONB NOT NULL DEFAULT '{}',
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  explicit BOOLEAN NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS smartbuy_recalculation_jobs (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id BIGINT NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  caused_by UUID NOT NULL REFERENCES smartbuy_feedback_events(feedback_event_id) ON DELETE CASCADE,
  stages JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (caused_by)
);

CREATE TABLE IF NOT EXISTS smartbuy_feedback_reviews (
  review_id TEXT PRIMARY KEY,
  feedback_event_id UUID REFERENCES smartbuy_feedback_events(feedback_event_id) ON DELETE CASCADE,
  property_id BIGINT NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  reviewer_user_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('APPROVE','REJECT','NEEDS_INFORMATION')),
  failure_stage TEXT NOT NULL,
  root_cause TEXT NOT NULL,
  expected_payload JSONB,
  evidence_ids JSONB NOT NULL DEFAULT '[]',
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_target ON smartbuy_feedback_events(property_id, target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_feedback_signal_target ON smartbuy_feedback_signals(property_id, target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_recalculation_queue ON smartbuy_recalculation_jobs(status, created_at);

CREATE OR REPLACE FUNCTION smartbuy_ingest_feedback(
  p_event JSONB,
  p_signal JSONB,
  p_command_hash TEXT,
  p_recalculation_stages JSONB
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE
  existing_event smartbuy_feedback_events%ROWTYPE;
BEGIN
  SELECT * INTO existing_event FROM smartbuy_feedback_events
   WHERE tenant_id = p_event->>'tenant_id'
     AND idempotency_key = p_event->>'idempotency_key';

  IF FOUND THEN
    IF existing_event.command_hash <> p_command_hash THEN
      RAISE EXCEPTION 'idempotency_conflict' USING ERRCODE = '23505';
    END IF;
    RETURN jsonb_build_object('status','already_processed');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM properties
     WHERE id = (p_event->>'property_id')::bigint
       AND user_id = auth.uid()
  ) THEN
    RAISE EXCEPTION 'property_not_found' USING ERRCODE = '23503';
  END IF;

  INSERT INTO smartbuy_feedback_events (
    feedback_event_id, property_id, tenant_id, actor_user_id, target_type,
    target_id, expected_version, action, origin, original_payload,
    corrected_payload, evidence_ids, document_id, analysis_result_id,
    rag_run_id, failure_stage, component_versions, reason, idempotency_key, command_hash
  ) VALUES (
    (p_event->>'feedback_event_id')::uuid, (p_event->>'property_id')::bigint,
    p_event->>'tenant_id', p_event->>'actor_user_id', p_event->>'target_type',
    p_event->>'target_id', p_event->>'expected_version', p_event->>'action',
    p_event->>'origin', p_event->'original_payload', p_event->'corrected_payload',
    COALESCE(p_event->'evidence_ids','[]'), p_event->>'document_id',
    p_event->>'analysis_result_id', p_event->>'rag_run_id',
    COALESCE(p_event->>'failure_stage','UNKNOWN'),
    COALESCE(p_event->'component_versions','{}'), p_event->>'reason',
    p_event->>'idempotency_key', p_command_hash
  );

  INSERT INTO smartbuy_feedback_signals (
    signal_id, feedback_event_id, property_id, target_type, target_id, kind,
    actor_id, actor_role, payload, expected_payload, evidence_ids, document_id,
    analysis_result_id, rag_run_id, component_versions, confidence, explicit, occurred_at
  ) VALUES (
    p_signal->>'signal_id', (p_signal->>'feedback_event_id')::uuid,
    (p_signal->>'property_id')::bigint, p_signal->>'target_type',
    p_signal->>'target_id', p_signal->>'kind', p_signal->>'actor_id',
    p_signal->>'actor_role', p_signal->'payload', p_signal->'expected_payload',
    COALESCE(p_signal->'evidence_ids','[]'), p_signal->>'document_id',
    p_signal->>'analysis_result_id', p_signal->>'rag_run_id',
    COALESCE(p_signal->'component_versions','{}'),
    (p_signal->>'confidence')::double precision,
    (p_signal->>'explicit')::boolean, (p_signal->>'occurred_at')::timestamptz
  );

  INSERT INTO smartbuy_recalculation_jobs(property_id, caused_by, stages)
  VALUES ((p_event->>'property_id')::bigint,
          (p_event->>'feedback_event_id')::uuid, p_recalculation_stages);

  RETURN jsonb_build_object('status','accepted');
END;
$$;

ALTER TABLE smartbuy_feedback_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE smartbuy_feedback_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE smartbuy_recalculation_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE smartbuy_feedback_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS feedback_event_owner_insert ON smartbuy_feedback_events;
DROP POLICY IF EXISTS feedback_event_owner_read ON smartbuy_feedback_events;
DROP POLICY IF EXISTS feedback_signal_owner_insert ON smartbuy_feedback_signals;
DROP POLICY IF EXISTS feedback_signal_owner_read ON smartbuy_feedback_signals;
DROP POLICY IF EXISTS feedback_job_owner_insert ON smartbuy_recalculation_jobs;
DROP POLICY IF EXISTS feedback_job_owner_read ON smartbuy_recalculation_jobs;
CREATE POLICY feedback_event_owner_insert ON smartbuy_feedback_events FOR INSERT
  WITH CHECK (actor_user_id = auth.uid()::text AND EXISTS (SELECT 1 FROM properties p WHERE p.id = property_id AND p.user_id = auth.uid()));
CREATE POLICY feedback_event_owner_read ON smartbuy_feedback_events FOR SELECT
  USING (actor_user_id = auth.uid()::text);
CREATE POLICY feedback_signal_owner_insert ON smartbuy_feedback_signals FOR INSERT
  WITH CHECK (actor_id = auth.uid()::text AND EXISTS (SELECT 1 FROM properties p WHERE p.id = property_id AND p.user_id = auth.uid()));
CREATE POLICY feedback_signal_owner_read ON smartbuy_feedback_signals FOR SELECT
  USING (actor_id = auth.uid()::text);
CREATE POLICY feedback_job_owner_insert ON smartbuy_recalculation_jobs FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM properties p WHERE p.id = property_id AND p.user_id = auth.uid()));
CREATE POLICY feedback_job_owner_read ON smartbuy_recalculation_jobs FOR SELECT
  USING (EXISTS (SELECT 1 FROM properties p WHERE p.id = property_id AND p.user_id = auth.uid()));
GRANT EXECUTE ON FUNCTION smartbuy_ingest_feedback(JSONB, JSONB, TEXT, JSONB) TO authenticated;
