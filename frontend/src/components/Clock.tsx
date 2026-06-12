import { useEffect, useState } from "react";

export function Clock() {
  const [time, setTime] = useState(() => new Date());

  useEffect(() => {
    const interval = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="font-mono text-sm text-slate-500">
      {time.toLocaleTimeString()}
    </div>
  );
}
