import api from "./api";


function dashboardCredential(
  credential
) {
  const token = String(
    credential || ""
  ).trim();

  if (token) {
    return token;
  }

  const error = new Error(
    "Dashboard credential is required."
  );

  error.code =
    "credential_required";

  throw error;
}


async function getDashboardResource(
  path,
  credential,
  {
    signal,
  } = {}
) {
  const token =
    dashboardCredential(
      credential
    );

  try {
    const response = await api.get(
      path,
      {
        signal,
        headers: {
          Authorization:
            `Bearer ${token}`,
        },
      }
    );

    return response.data;
  } catch (requestError) {
    const error = new Error(
      "Dashboard request failed."
    );

    error.status = Number(
      requestError?.response?.status ||
        0
    );

    throw error;
  }
}


export async function getDashboardSummary(
  credential,
  options = {}
) {
  return getDashboardResource(
    "/admin/dashboard/summary",
    credential,
    options
  );
}


export async function getDashboardHealth(
  credential,
  options = {}
) {
  return getDashboardResource(
    "/admin/dashboard/health",
    credential,
    options
  );
}


export async function getDashboardActivityToday(
  credential,
  options = {}
) {
  const data =
    await getDashboardResource(
      "/admin/dashboard/activity/today",
      credential,
      options
    );

  if (
    !data ||
    data.service !==
      "dashboard_activity" ||
    !data.activity ||
    typeof data.activity !== "object"
  ) {
    const error = new Error(
      "Invalid activity payload structure"
    );
    error.status = 0;
    throw error;
  }

  const act = data.activity;

  const normalizeCount = (val) => {
    const num = Number(val);
    return Number.isFinite(num) &&
      num >= 0
      ? Math.floor(num)
      : 0;
  };

  const rawBuckets = Array.isArray(
    act.buckets
  )
    ? act.buckets
    : [];

  const buckets = rawBuckets
    .slice(0, 6)
    .map((b) => ({
      start: String(b?.start || ""),
      end_exclusive: String(
        b?.end_exclusive || ""
      ),
      message_count: normalizeCount(
        b?.message_count
      ),
    }));

  const messages = act.messages || {};

  return {
    service: String(
      data.service || ""
    ),
    activity: {
      scope: String(
        act.scope || "conversation"
      ),
      day: String(act.day || ""),
      day_basis: String(
        act.day_basis ||
          "server_local_calendar_day"
      ),
      start: String(
        act.start || ""
      ),
      end_exclusive: String(
        act.end_exclusive || ""
      ),
      bucket_hours: normalizeCount(
        act.bucket_hours
      ),
      messages: {
        total: normalizeCount(
          messages.total
        ),
        user: normalizeCount(
          messages.user
        ),
        assistant: normalizeCount(
          messages.assistant
        ),
        other: normalizeCount(
          messages.other
        ),
      },
      buckets,
    },
  };
}
