export default function pcmToWav(
  audioDataBuffer: ArrayBuffer,
  sampleRate: number,
  numChannels: number = 1
) {
  const dataSize = audioDataBuffer.byteLength;
  const bitsPerSample = 16; // Standard for PCM

  // Create buffer
  const buffer = new ArrayBuffer(44 + dataSize); // Headers (44) + audio data
  const view = new DataView(buffer);

  // Write RIFF header
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  writeString(8, "WAVE");

  // Write fmt subchunk
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
  view.setUint16(20, 1, true); // AudioFormat (1 for PCM)
  view.setUint16(22, numChannels, true); // NumChannels
  view.setUint32(24, sampleRate, true); // SampleRate

  // ByteRate = SampleRate * NumChannels * BitsPerSample/8
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  view.setUint32(28, byteRate, true);

  // BlockAlign = NumChannels * BitsPerSample/8
  const blockAlign = numChannels * (bitsPerSample / 8);
  view.setUint16(32, blockAlign, true);

  view.setUint16(34, bitsPerSample, true); // BitsPerSample

  // Write data subchunk
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  // Copy the audio data to the buffer
  new Uint8Array(buffer, 44).set(new Uint8Array(audioDataBuffer));

  return buffer;
}
