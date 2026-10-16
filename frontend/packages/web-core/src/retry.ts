export function describeRetry(seconds: number): string {
  if (seconds < 90) {
    return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  }
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} minutes`;
}
