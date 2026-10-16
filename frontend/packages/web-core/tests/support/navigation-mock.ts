export const router = {
  push: jest.fn(),
  replace: jest.fn(),
  refresh: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  prefetch: jest.fn(),
};

export const useRouter = () => router;

export const redirect = (path: string): never => {
  throw new Error(`NEXT_REDIRECT ${path}`);
};

export const notFound = (): never => {
  throw new Error("NEXT_NOT_FOUND");
};

export function resetRouter(): void {
  for (const fn of Object.values(router)) {
    fn.mockReset();
  }
}
