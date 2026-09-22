import { render, screen } from "@testing-library/react";

function Greeting({ name }: { name: string }) {
  return <p>Hello, {name}!</p>;
}

describe("test harness smoke test", () => {
  it("renders with React Testing Library and asserts via jest-dom matchers", () => {
    render(<Greeting name="Deadbot" />);

    const message = screen.getByText("Hello, Deadbot!");
    expect(message).toBeInTheDocument();
  });
});
