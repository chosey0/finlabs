import { cleanup, render, screen } from "@testing-library/react";
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
});
