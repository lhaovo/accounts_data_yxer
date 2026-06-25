export const state = {
  mode: "single",
  status: null,
  lastRows: [],
  sortKey: "metric_date",
  sortDir: "asc",
};

export const numericColumns = new Set(["fans", "play", "like", "comment", "collect", "publish_count"]);

export const totalTargets = {
  fans: "totalFans",
  play: "totalPlay",
  like: "totalLike",
  comment: "totalComment",
  collect: "totalCollect",
  publish_count: "totalPublish",
};
