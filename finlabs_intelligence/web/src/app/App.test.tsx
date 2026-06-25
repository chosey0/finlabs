import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";

afterEach(cleanup);

describe("App composition root", () => {
  it("renders the workbench shell with the three workflow panels", () => {
    render(<App />);

    // Header + status mirror the sidebar-layout e2e expectations.
    expect(screen.getByText("FINLABS · LOCAL DATA WORKBENCH")).toBeTruthy();
    expect(screen.getByText("종목을 검색하세요.")).toBeTruthy();
    expect(screen.queryAllByRole("heading", { level: 1 })).toHaveLength(0);

    // Each workflow step is its own feature panel by accessible region/name.
    expect(screen.getByRole("complementary", { name: "국내 종목 선택" })).toBeTruthy();
    expect(screen.getByRole("region", { name: /차트 관측 시점/ })).toBeTruthy();
    expect(screen.getByRole("region", { name: /검색 뉴스/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "검색" })).toBeTruthy();
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
