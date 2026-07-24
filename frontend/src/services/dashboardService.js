import api from "./api";


export async function getDashboardSummary(
  credential,
  {
    signal,
  } = {}
) {
  const token = String(
    credential || ""
  ).trim();

  if (!token) {
    const error = new Error(
      "Dashboard credential is required."
    );

    error.code =
      "credential_required";

    throw error;
  }

  try {
    const response = await api.get(
      "/admin/dashboard/summary",
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
