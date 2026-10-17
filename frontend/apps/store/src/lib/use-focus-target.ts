import { useEffect, useState } from "react";

export function useFocusTarget(): (elementId: string) => void {
  const [target, setTarget] = useState<{ elementId: string }>();

  useEffect(() => {
    if (target) {
      document.getElementById(target.elementId)?.focus();
    }
  }, [target]);

  return (elementId) => {
    setTarget({ elementId });
  };
}
