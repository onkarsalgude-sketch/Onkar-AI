import axios from "axios";

const API = import.meta.env.VITE_API_URL;

export async function analyzeImage(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await axios.post(
    `${API}/image/analyze`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );

  return res.data;
}