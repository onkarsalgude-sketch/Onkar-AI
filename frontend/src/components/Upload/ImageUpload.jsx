import { useState } from "react";
import { analyzeImage } from "../../services/imageService";

function ImageUpload() {
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState("");
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);

  async function upload(e) {
    const file = e.target.files[0];

    if (!file) return;

    setImage(file);
    setPreview(URL.createObjectURL(file));

    setLoading(true);

    try {
      const res = await analyzeImage(file);

      setResult(res.result);
    } catch (err) {
      console.log(err);
      setResult("❌ Image analysis failed.");
    }

    setLoading(false);
  }

  return (
    <div className="bg-slate-900 rounded-xl p-5">

      <input
        type="file"
        accept="image/*"
        onChange={upload}
      />

      {preview && (
        <img
          src={preview}
          alt=""
          className="mt-4 rounded-xl max-h-72"
        />
      )}

      {loading && (
        <p className="mt-4">
          🤖 Analyzing image...
        </p>
      )}

      {result && (
        <div className="mt-4 bg-slate-800 p-4 rounded-xl">
          {result}
        </div>
      )}

    </div>
  );
}

export default ImageUpload;