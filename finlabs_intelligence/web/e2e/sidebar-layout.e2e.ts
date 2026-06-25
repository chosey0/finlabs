import { expect, test } from "@playwright/test";

test("two-pane workbench: command bar on top, chart and news side by side", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");

  await expect(page.locator("main > header")).toHaveCount(1);
  await expect(page.locator("main > header")).toContainText("FINLABS · LOCAL DATA WORKBENCH");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(0);
  await expect(page.locator("p.lede")).toHaveCount(0);

  const header = page.locator("main > header");
  const chart = page.getByRole("region", { name: "차트" });
  const news = page.getByRole("region", { name: "뉴스" });
  const status = page.locator("p.status");

  await expect(status).toHaveAttribute("role", "status");
  await expect(status).toContainText("종목을 검색하세요.");
  await expect(page.getByLabel("종목명 또는 종목코드")).toBeVisible();
  await expect(page.getByTestId("selected-candle")).toBeVisible();
  await expect(news).toContainText("캔들을 선택한 뒤 뉴스 검색을 실행하세요.");

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

  const headerBox = await header.boundingBox();
  const chartBox = await chart.boundingBox();
  const newsBox = await news.boundingBox();
  expect(headerBox).not.toBeNull();
  expect(chartBox).not.toBeNull();
  expect(newsBox).not.toBeNull();
  // Command bar sits above the panes; chart is left of news and top-aligned.
  expect(headerBox!.y + headerBox!.height).toBeLessThanOrEqual(chartBox!.y + 1);
  expect(chartBox!.x + chartBox!.width).toBeLessThanOrEqual(newsBox!.x + 1);
  expect(Math.abs(chartBox!.y - newsBox!.y)).toBeLessThanOrEqual(2);

  const loadChartButton = await page.getByRole("button", { name: "차트 불러오기" }).boundingBox();
  const discoverNewsButton = await page.getByRole("button", { name: "선택 구간 뉴스 검색" }).boundingBox();
  expect(loadChartButton!.x + loadChartButton!.width).toBeLessThanOrEqual(discoverNewsButton!.x + 1);
  expect(loadChartButton!.y).toBe(discoverNewsButton!.y);
  // The desktop workbench fits the viewport without page scroll.
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(900);

  await page.setViewportSize({ width: 800, height: 900 });
  const mobileChart = await chart.boundingBox();
  const mobileNews = await news.boundingBox();
  expect(mobileChart).not.toBeNull();
  expect(mobileNews).not.toBeNull();
  // Narrow screens stack the panes (chart above news) without horizontal scroll.
  expect(mobileChart!.y + mobileChart!.height).toBeLessThanOrEqual(mobileNews!.y + 1);
  expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(800);
});
