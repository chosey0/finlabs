import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";

afterEach(cleanup);

describe("App composition root", () => {
  it("renders the command bar, bridge, and two-pane workbench", () => {
    render(<App />);

    // Header + status mirror the layout e2e expectations.
    expect(screen.getByText("FINLABS · LOCAL DATA WORKBENCH")).toBeTruthy();
    expect(screen.getByText("종목을 검색하세요.")).toBeTruthy();
    expect(screen.queryAllByRole("heading", { level: 1 })).toHaveLength(0);

    // Command-bar search plus the two co-visible panes.
    expect(screen.getByLabelText("종목명 또는 종목코드")).toBeTruthy();
    expect(screen.getByRole("button", { name: "검색" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "차트" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "뉴스" })).toBeTruthy();
    expect(screen.getByTestId("selected-candle")).toBeTruthy();
  });

  it("starts in the empty chart and news states", () => {
    render(<App />);

    expect(
      screen.getByText("종목과 조회 범위를 선택하면 Kiwoom 차트를 표시합니다."),
    ).toBeTruthy();
    expect(
      screen.getByText("캔들을 선택한 뒤 뉴스 검색을 실행하세요."),
    ).toBeTruthy();
  });

  it("activates the bridge from a typed news window without a candle click", () => {
    render(<App />);

    const bridge = screen.getByTestId("selected-candle");
    expect(bridge.className).not.toContain("active");

    fireEvent.change(screen.getByLabelText("뉴스 구간 시작"), {
      target: { value: "2026-06-17T08:31" },
    });
    fireEvent.change(screen.getByLabelText("뉴스 구간 끝 t0"), {
      target: { value: "2026-06-17T09:31" },
    });
    fireEvent.click(screen.getByRole("button", { name: "구간 적용" }));

    expect(bridge.className).toContain("active");
    expect(bridge.textContent).toContain("뉴스 검색 구간");
    expect(screen.getByText(/뉴스 구간을 직접 설정했습니다/)).toBeTruthy();
  });

  it("rejects a typed window whose start is not before t0", () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("뉴스 구간 시작"), {
      target: { value: "2026-06-17T09:31" },
    });
    fireEvent.change(screen.getByLabelText("뉴스 구간 끝 t0"), {
      target: { value: "2026-06-17T08:31" },
    });
    fireEvent.click(screen.getByRole("button", { name: "구간 적용" }));

    expect(screen.getByTestId("selected-candle").className).not.toContain("active");
    expect(
      screen.getByText("뉴스 구간의 시작은 끝(t0)보다 앞서야 합니다."),
    ).toBeTruthy();
  });
});
