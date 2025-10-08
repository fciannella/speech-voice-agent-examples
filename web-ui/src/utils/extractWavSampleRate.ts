export default function extractWavSampleRate(arrayBuffer: ArrayBuffer): number {
  const dataView = new DataView(arrayBuffer);

  // Check if the file is a valid WAV file
  const riff = String.fromCharCode(
    dataView.getUint8(0),
    dataView.getUint8(1),
    dataView.getUint8(2),
    dataView.getUint8(3)
  );
  const wave = String.fromCharCode(
    dataView.getUint8(8),
    dataView.getUint8(9),
    dataView.getUint8(10),
    dataView.getUint8(11)
  );
  if (riff !== "RIFF" || wave !== "WAVE") {
    throw new Error("Invalid WAV file");
  }

  return dataView.getUint32(24, true);
}
