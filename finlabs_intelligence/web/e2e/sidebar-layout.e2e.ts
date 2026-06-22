import { expect, test } from "@playwright/test";

test("security selector uses a desktop sidebar and stacks on narrow screens", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");

  await expect(page.locator("main > header")).toHaveCount(1);
  await expect(page.locator("main > header")).toContainText("FINLABS · LOCAL DATA WORKBENCH");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(0);
  await expect(page.locator("p.lede")).toHaveCount(0);
  const sidebar = page.getByRole("complementary", { name: "국내 종목 선택" });
  const chartPanel = page.getByRole("region", { name: "차트 관측 시점" });
  const newsPanel = page.getByRole("region", { name: "검색 뉴스" });
  const status = page.locator("p.status");
  const desktopSidebar = await sidebar.boundingBox();
  const desktopChart = await chartPanel.boundingBox();
  const desktopNews = await newsPanel.boundingBox();
  const desktopStatus = await status.boundingBox();

  expect(desktopSidebar).not.toBeNull();
  expect(desktopChart).not.toBeNull();
  expect(desktopNews).not.toBeNull();
  expect(desktopStatus).not.toBeNull();
  expect(desktopStatus!.y + desktopStatus!.height).toBeLessThanOrEqual(desktopSidebar!.y);
  await expect(status).toHaveAttribute("role", "status");
  await expect(status).toContainText("종목을 검색하세요.");
  const todayKst = await page.evaluate(() => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  });
  await expect(page.getByLabel("시작")).toHaveValue(`${todayKst}T09:00`);
  await expect(page.getByLabel("종료")).toHaveValue(`${todayKst}T15:30`);
  expect(desktopSidebar!.x + desktopSidebar!.width).toBeLessThan(desktopChart!.x);
  expect(Math.abs(desktopChart!.x - desktopNews!.x)).toBeLessThanOrEqual(1);
  expect(desktopChart!.y + desktopChart!.height).toBeLessThan(desktopNews!.y);
  await expect(newsPanel).toContainText("캔들을 선택한 뒤 뉴스 검색을 실행하세요.");
  const loadChartButton = await page.getByRole("button", { name: "차트 불러오기" }).boundingBox();
  const discoverNewsButton = await page.getByRole("button", { name: "선택 구간 뉴스 검색" }).boundingBox();
  expect(loadChartButton).not.toBeNull();
  expect(discoverNewsButton).not.toBeNull();
  expect(loadChartButton!.x + loadChartButton!.width).toBeLessThan(discoverNewsButton!.x);
  expect(loadChartButton!.y).toBe(discoverNewsButton!.y);
  await expect(page.getByTestId("work-area")).toHaveCSS("overflow-y", "auto");
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900);

  const chartToggle = page.getByRole("button", { name: "차트 관측 시점", exact: true });
  await expect(chartToggle).toHaveAttribute("aria-expanded", "true");
  await chartToggle.click();
  await expect(chartToggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#chart-accordion-content")).toBeHidden();
  await expect(page.getByLabel("차트 종류")).toBeVisible();
  await expect(page.getByRole("button", { name: "차트 불러오기" })).toBeVisible();
  await expect(page.getByTestId("selected-candle")).toBeVisible();
  await chartToggle.click();
  await expect(page.locator("#chart-accordion-content")).toBeVisible();

  const newsToggle = page.getByRole("button", { name: "검색 뉴스", exact: true });
  await expect(newsToggle).toHaveAttribute("aria-expanded", "true");
  await newsToggle.click();
  await expect(newsToggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#news-accordion-content")).toBeHidden();
  await newsToggle.click();
  await expect(page.locator("#news-accordion-content")).toBeVisible();

  await page.setViewportSize({ width: 800, height: 900 });
  const mobileSidebar = await sidebar.boundingBox();
  const mobileChart = await chartPanel.boundingBox();
  const mobileNews = await newsPanel.boundingBox();

  expect(mobileSidebar).not.toBeNull();
  expect(mobileChart).not.toBeNull();
  expect(mobileNews).not.toBeNull();
  expect(mobileSidebar!.y + mobileSidebar!.height).toBeLessThan(mobileChart!.y);
  expect(mobileChart!.y + mobileChart!.height).toBeLessThan(mobileNews!.y);
  await expect(page.getByTestId("workspace-columns")).toHaveCSS("overflow-y", "auto");
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900);
  expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(800);
});
