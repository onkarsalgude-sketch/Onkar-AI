function DropZone({ uploadPDF }) {
  function handleDrop(e) {
    e.preventDefault();

    const file = e.dataTransfer.files[0];

    if (!file) return;

    uploadPDF({
      target: {
        files: [file],
      },
    });
  }

  function handleDragOver(e) {
    e.preventDefault();
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      className="border-2 border-dashed border-slate-600 rounded-2xl p-8 text-center text-slate-400 hover:border-blue-500 hover:bg-slate-900 transition cursor-pointer"
    >
      <div className="text-5xl mb-4">📄</div>

      <h3 className="text-lg font-semibold text-white">
        Drag & Drop PDF Here
      </h3>

      <p className="mt-2">
        or use the Upload PDF button
      </p>
    </div>
  );
}

export default DropZone;