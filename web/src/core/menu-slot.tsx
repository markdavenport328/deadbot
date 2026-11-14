import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// A place at the top of the site menu that other parts of the app can fill
// (the workspace puts its history there). Without a provider every piece is a
// harmless no-op, so the menu works exactly as before.
// The setter and the node live in separate contexts so a component that fills
// the slot does not re-render when the slot changes (that would loop).
const SetSlotContext = createContext<(node: ReactNode | null) => void>(() => {});
const SlotNodeContext = createContext<ReactNode | null>(null);
const CloseContext = createContext<() => void>(() => {});

export function MenuSlotProvider({ children }: { children: ReactNode }) {
  const [node, setNode] = useState<ReactNode | null>(null);
  return (
    <SetSlotContext.Provider value={setNode}>
      <SlotNodeContext.Provider value={node}>{children}</SlotNodeContext.Provider>
    </SetSlotContext.Provider>
  );
}

export function useMenuSlot(node: ReactNode | null): void {
  const setNode = useContext(SetSlotContext);
  useEffect(() => {
    setNode(node);
    return () => setNode(null);
  }, [node, setNode]);
}

export function MenuSlotOutlet() {
  return <>{useContext(SlotNodeContext)}</>;
}

export const CloseSiteMenuProvider = CloseContext.Provider;

export function useCloseSiteMenu(): () => void {
  return useContext(CloseContext);
}
