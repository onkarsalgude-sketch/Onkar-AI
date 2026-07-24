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
