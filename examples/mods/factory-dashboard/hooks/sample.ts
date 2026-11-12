// What scripts/dashboard_data.py's build() printed in tests/test_dashboard_data.py's Sample. Don't edit it:
// UPDATE_SAMPLE=1 python3 -m unittest tests.test_dashboard_data.Sample writes it again.
import type { Doc } from '../types'

export const SAMPLE: Doc = {
  "activity": {
    "agent_spend": {
      "reviewer": {
        "cost_usd": 0.4575,
        "tokens": 305000
      }
    },
    "agents": {
      "reviewer": 2,
      "security-reviewer": 1
    },
    "asks": 2,
    "chain": "unchained",
    "command_spend": {
      "standup": {
        "cost_usd": 62.115,
        "tokens": 8200000
      }
    },
    "commands": {
      "standup": 9
    },
    "guard_refusals": {
      "credential-file": 1
    },
    "prices_checked": "2026-10-01",
    "skill_spend": {
      "review-pr": {
        "cost_usd": 0.615,
        "tokens": 410000
      }
    },
    "skills": {
      "learn": 2,
      "review-pr": 9
    },
    "spend_at": "2026-10-27T12:00:00+00:00",
    "unpriced": {}
  },
  "conversations": {
    "factory": {
      "by_day": [
        {
          "day": "2026-10-15",
          "tokens": 1575000
        },
        {
          "day": "2026-10-16",
          "tokens": 4410000
        },
        {
          "day": "2026-10-17",
          "tokens": 0
        },
        {
          "day": "2026-10-18",
          "tokens": 0
        },
        {
          "day": "2026-10-19",
          "tokens": 3990000
        },
        {
          "day": "2026-10-20",
          "tokens": 6405000
        },
        {
          "day": "2026-10-21",
          "tokens": 5460000
        },
        {
          "day": "2026-10-22",
          "tokens": 7350000
        },
        {
          "day": "2026-10-23",
          "tokens": 4725000
        },
        {
          "day": "2026-10-24",
          "tokens": 945000
        },
        {
          "day": "2026-10-25",
          "tokens": 0
        },
        {
          "day": "2026-10-26",
          "tokens": 8610000
        },
        {
          "day": "2026-10-27",
          "tokens": 5880000
        }
      ],
      "by_model": {
        "claude-haiku-5-5": {
          "cache_reads": 940000,
          "cache_writes": 705000,
          "input": 235000,
          "output": 470000,
          "total": 2350000
        },
        "claude-opus-5-5": {
          "cache_reads": 18800000,
          "cache_writes": 14100000,
          "input": 4700000,
          "output": 9400000,
          "total": 47000000
        }
      },
      "sessions": 10
    },
    "loop": {
      "by_day": [
        {
          "day": "2026-10-15",
          "tokens": 0
        },
        {
          "day": "2026-10-16",
          "tokens": 2100000
        },
        {
          "day": "2026-10-17",
          "tokens": 0
        },
        {
          "day": "2026-10-18",
          "tokens": 0
        },
        {
          "day": "2026-10-19",
          "tokens": 2800000
        },
        {
          "day": "2026-10-20",
          "tokens": 0
        },
        {
          "day": "2026-10-21",
          "tokens": 3300000
        },
        {
          "day": "2026-10-22",
          "tokens": 0
        },
        {
          "day": "2026-10-23",
          "tokens": 5200000
        },
        {
          "day": "2026-10-24",
          "tokens": 0
        },
        {
          "day": "2026-10-25",
          "tokens": 0
        },
        {
          "day": "2026-10-26",
          "tokens": 2400000
        },
        {
          "day": "2026-10-27",
          "tokens": 2600000
        }
      ],
      "by_model": {
        "claude-opus-5-5": {
          "cache_reads": 7360000,
          "cache_writes": 5520000,
          "input": 1840000,
          "output": 3680000,
          "total": 18400000
        }
      },
      "sessions": 6
    }
  },
  "evals": {
    "reviewer": {
      "changed": [
        "briefs/proposal.md"
      ],
      "failing": 0,
      "failing_cases": [],
      "flaky": 1,
      "newest_change": "2026-10-26T12:00:00+00:00",
      "saved": "2026-10-25T09:00:00+00:00",
      "stable": 9,
      "stale": true
    },
    "security-reviewer": {
      "changed": [],
      "failing": 0,
      "failing_cases": [],
      "flaky": 0,
      "newest_change": null,
      "saved": "2026-10-26T09:00:00+00:00",
      "stable": 8,
      "stale": false
    }
  },
  "generated": "2026-10-27T12:00:00+00:00",
  "loop_history": {
    "by_day": [
      {
        "blocked": 0,
        "day": "2026-10-15",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-16",
        "more_than_one_round": 0,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-17",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-18",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-19",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-20",
        "more_than_one_round": 0,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-21",
        "more_than_one_round": 1,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-22",
        "more_than_one_round": 0,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 1,
        "day": "2026-10-23",
        "more_than_one_round": 1,
        "pr": 0,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-24",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-25",
        "more_than_one_round": 0,
        "pr": 0,
        "runs": 0,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-26",
        "more_than_one_round": 0,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      },
      {
        "blocked": 0,
        "day": "2026-10-27",
        "more_than_one_round": 0,
        "pr": 1,
        "runs": 1,
        "skipped": 0,
        "stopped": 0
      }
    ],
    "by_outcome": {
      "blocked": 1,
      "pr": 6,
      "skipped": 0,
      "stopped": 0
    },
    "runs": [
      {
        "cost_usd": 3.65,
        "ended": "2026-10-16T10:40:00",
        "issue": "issue-31",
        "outcome": "pr",
        "rounds": 1,
        "started": "2026-10-16T09:00:00",
        "tests": [
          "passed"
        ],
        "tokens": 2440000,
        "verdicts": [
          "PASS"
        ]
      },
      {
        "cost_usd": 4.75,
        "ended": "2026-10-20T09:40:00",
        "issue": "issue-32",
        "outcome": "pr",
        "rounds": 1,
        "started": "2026-10-19T09:00:00",
        "tests": [
          "passed"
        ],
        "tokens": 3220000,
        "verdicts": [
          "PASS"
        ]
      },
      {
        "cost_usd": 6.3,
        "ended": "2026-10-21T10:30:00",
        "issue": "issue-33",
        "outcome": "pr",
        "rounds": 2,
        "started": "2026-10-20T11:00:00",
        "tests": [
          "failed",
          "passed"
        ],
        "tokens": 4240000,
        "verdicts": [
          "FIX",
          "PASS"
        ]
      },
      {
        "cost_usd": 1.3,
        "ended": "2026-10-22T15:10:00",
        "issue": "app/issue-3",
        "outcome": "pr",
        "rounds": 1,
        "started": "2026-10-22T14:00:00",
        "tests": [
          "passed"
        ],
        "tokens": 880000,
        "verdicts": [
          "PASS"
        ]
      },
      {
        "cost_usd": 9.15,
        "ended": "2026-10-23T16:00:00",
        "issue": "issue-34",
        "outcome": "blocked",
        "rounds": 5,
        "started": "2026-10-22T09:00:00",
        "tests": [
          "failed",
          "failed",
          "failed",
          "failed",
          "failed"
        ],
        "tokens": 6160000,
        "verdicts": [
          "FIX",
          "FIX",
          "FIX",
          "FIX",
          "FIX"
        ]
      },
      {
        "cost_usd": 4.2,
        "ended": "2026-10-26T11:00:00",
        "issue": "issue-36",
        "outcome": "pr",
        "rounds": 1,
        "started": "2026-10-26T09:00:00",
        "tests": [
          "passed"
        ],
        "tokens": 2820000,
        "verdicts": [
          "PASS"
        ]
      },
      {
        "cost_usd": 4.5,
        "ended": "2026-10-27T08:48:00",
        "issue": "issue-38",
        "outcome": "pr",
        "rounds": 1,
        "started": "2026-10-26T13:00:00",
        "tests": [
          "passed"
        ],
        "tokens": 3020000,
        "verdicts": [
          "PASS"
        ]
      }
    ],
    "skipped_lines": 0
  },
  "loop_rework": {
    "merged": 3,
    "pull_requests": [
      {
        "merges_from_base": 0,
        "number": 41,
        "other_commits": 1,
        "title": "Loop: say which round a review was"
      },
      {
        "merges_from_base": 1,
        "number": 43,
        "other_commits": 0,
        "title": "Gate: name the section that's empty"
      }
    ],
    "reworked": 2
  },
  "loop_spend": {
    "by_day": [
      {
        "cost_usd": 0.0,
        "day": "2026-10-15",
        "tokens": 0
      },
      {
        "cost_usd": 3.65,
        "day": "2026-10-16",
        "tokens": 2440000
      },
      {
        "cost_usd": 0.0,
        "day": "2026-10-17",
        "tokens": 0
      },
      {
        "cost_usd": 0.0,
        "day": "2026-10-18",
        "tokens": 0
      },
      {
        "cost_usd": 4.15,
        "day": "2026-10-19",
        "tokens": 2820000
      },
      {
        "cost_usd": 4.0,
        "day": "2026-10-20",
        "tokens": 2690000
      },
      {
        "cost_usd": 2.9,
        "day": "2026-10-21",
        "tokens": 1950000
      },
      {
        "cost_usd": 5.8,
        "day": "2026-10-22",
        "tokens": 3910000
      },
      {
        "cost_usd": 4.65,
        "day": "2026-10-23",
        "tokens": 3130000
      },
      {
        "cost_usd": 0.0,
        "day": "2026-10-24",
        "tokens": 0
      },
      {
        "cost_usd": 0.0,
        "day": "2026-10-25",
        "tokens": 0
      },
      {
        "cost_usd": 4.9,
        "day": "2026-10-26",
        "tokens": 3290000
      },
      {
        "cost_usd": 4.55,
        "day": "2026-10-27",
        "tokens": 3050000
      }
    ],
    "by_issue": {
      "app/issue-3": {
        "cost_usd": 1.3,
        "tokens": 880000
      },
      "issue-31": {
        "cost_usd": 3.65,
        "tokens": 2440000
      },
      "issue-32": {
        "cost_usd": 4.75,
        "tokens": 3220000
      },
      "issue-33": {
        "cost_usd": 6.3,
        "tokens": 4240000
      },
      "issue-34": {
        "cost_usd": 9.15,
        "tokens": 6160000
      },
      "issue-36": {
        "cost_usd": 4.2,
        "tokens": 2820000
      },
      "issue-38": {
        "cost_usd": 4.5,
        "tokens": 3020000
      },
      "issue-40": {
        "cost_usd": 0.75,
        "tokens": 500000
      }
    },
    "by_model": {
      "claude-opus-5-5": {
        "cost_usd": 25.6,
        "label": "claude-opus-5-5",
        "tokens": 17250000
      },
      "claude-sonnet-5-5": {
        "cost_usd": 9.0,
        "label": "claude-sonnet-5-5",
        "tokens": 6030000
      }
    },
    "by_step": {
      "build": {
        "cost_usd": 25.6,
        "tokens": 17250000
      },
      "plan": {
        "cost_usd": 5.75,
        "tokens": 3880000
      },
      "review": {
        "cost_usd": 3.25,
        "tokens": 2150000
      }
    },
    "cost_per_pr": 5.7667,
    "first_run": "2026-10-16",
    "last_7_days": {
      "cost_usd": 22.8,
      "tokens": 15330000
    },
    "since": {
      "cost_usd": 34.6,
      "tokens": 23280000
    },
    "today": {
      "cost_usd": 4.55,
      "tokens": 3050000
    }
  },
  "loop_throughput": {
    "by_state": {
      "blocked": 1,
      "building": 1,
      "pr": 6
    },
    "issues": 8,
    "more_than_one_round": 2,
    "rounds": {
      "app/issue-3": 1,
      "issue-31": 1,
      "issue-32": 1,
      "issue-33": 2,
      "issue-34": 5,
      "issue-36": 1,
      "issue-38": 1,
      "issue-40": 1
    }
  },
  "schema": 2,
  "since": "2026-10-15",
  "stage_times": {
    "loop_steps": {
      "BUILD": {
        "issues": 7,
        "median_minutes": 23.3
      },
      "SCALE": {
        "issues": 6,
        "median_minutes": 1.2
      },
      "SHAPE": {
        "issues": 8,
        "median_minutes": 4.2
      },
      "VALIDATE": {
        "issues": 7,
        "median_minutes": 58.3
      }
    },
    "pull_requests": {
      "median_hours_to_first_review": 4.5,
      "median_hours_to_merge": 25.3,
      "merged": 3,
      "reviewed": 3
    },
    "slowest": "merge"
  },
  "waiting": {
    "blocked": [
      {
        "issue": "issue-34",
        "note": "the link check still fails after 5 rounds",
        "number": 34,
        "title": "README: link the loop section",
        "updated": "2026-10-23T16:00:00Z"
      }
    ],
    "pull_requests": [
      {
        "checks": "pass",
        "conflicts": false,
        "draft": false,
        "hours_waited": 3.2,
        "loop_issue": 38,
        "number": 45,
        "opened": "2026-10-27T08:48:00Z",
        "title": "Gate: check the fee total"
      },
      {
        "checks": "pending",
        "conflicts": null,
        "draft": false,
        "hours_waited": 25.0,
        "loop_issue": 36,
        "number": 44,
        "opened": "2026-10-26T11:00:00Z",
        "title": "Loop: retry a flaky test once"
      },
      {
        "checks": "fail",
        "conflicts": true,
        "draft": true,
        "hours_waited": 48.0,
        "loop_issue": null,
        "number": 42,
        "opened": "2026-10-25T12:00:00Z",
        "title": "Steering: shorter replies"
      },
      {
        "checks": null,
        "conflicts": false,
        "draft": false,
        "hours_waited": 1.0,
        "loop_issue": null,
        "number": 46,
        "opened": "2026-10-27T11:00:00Z",
        "title": "Examples: a Go project"
      }
    ]
  },
  "work_by_type": {
    "truncated": false,
    "types": [
      {
        "cost_usd": 4.75,
        "issues": 1,
        "loop_built": 1,
        "merged": 1,
        "tokens": 3220000,
        "type": "bug"
      },
      {
        "cost_usd": 9.95,
        "issues": 2,
        "loop_built": 2,
        "merged": 2,
        "tokens": 6680000,
        "type": "enhancement"
      },
      {
        "cost_usd": 0.0,
        "issues": 0,
        "loop_built": 0,
        "merged": 1,
        "tokens": 0,
        "type": "documentation"
      },
      {
        "cost_usd": 0.0,
        "issues": 0,
        "loop_built": 0,
        "merged": 0,
        "tokens": 0,
        "type": "chore"
      },
      {
        "cost_usd": 0.0,
        "issues": 0,
        "loop_built": 0,
        "merged": 1,
        "tokens": 0,
        "type": null
      }
    ]
  }
}
