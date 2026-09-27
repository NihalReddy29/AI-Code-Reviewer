export type Finding = {
  id: string;
  file: string;
  line: number | null;
  category: string;
  severity: string;
  title: string;
  description: string;
  evidence: string | null;
  suggested_fix: string | null;
  confidence: number;
  verified: boolean | null;
  verification_reason: string | null;
};

export type ChangedFile = {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  language: string | null;
  kind: string | null;
  patch: string | null;
  sensitive_areas: string[];
};

export type ToolIssue = {
  tool: string;
  file: string;
  line: number | null;
  rule: string | null;
  message: string;
  severity: string | null;
};

export type ToolRun = {
  tool: string;
  available: boolean;
  exit_code: number | null;
  issues: ToolIssue[];
  error: string | null;
};

export type StaticAnalysis = {
  workspace_files: string[];
  runs: ToolRun[];
};

export type TestCase = {
  nodeid: string;
  file: string | null;
  outcome: string;
  message: string | null;
};

export type TestResults = {
  runner: string;
  available: boolean;
  skipped: boolean;
  skip_reason: string | null;
  discovered: string[];
  passed: number;
  failed: number;
  errors: number;
  skipped_cases: number;
  cases: TestCase[];
  error: string | null;
};

export type RetrievedChunk = {
  file_path: string;
  symbol: string | null;
  start_line: number;
  end_line: number;
  score: number;
  text: string;
};

export type RepositoryContext = {
  primary_language: string | null;
  project_types: string[];
  package_managers: string[];
  test_frameworks: string[];
  file_count: number;
};

export type ReviewSummary = {
  id: string;
  status: string;
  trigger: string;
  commit_sha: string;
  repository: string;
  pull_request: number;
  title: string;
  author: string | null;
  source_branch: string | null;
  target_branch: string | null;
  finding_count: number;
  verified_count: number;
  posted_to_github: boolean;
  github_review_id: number | null;
  execution_time_ms: number | null;
  created_at: string | null;
  finished_at: string | null;
};

export type ReviewDetail = ReviewSummary & {
  summary: string | null;
  changed_files: ChangedFile[];
  repository_context: RepositoryContext | null;
  retrieved_context: RetrievedChunk[];
  static_analysis: StaticAnalysis | null;
  test_results: TestResults | null;
  agent_trace: Array<Record<string, unknown>>;
  findings: Finding[];
  errors: unknown;
  started_at: string | null;
};

export type HealthStatus = {
  status: string;
  database: string;
  service: string;
};
