import { expect, test } from "@playwright/test";

test("real FastAPI and DuckDB labeling workflow", async ({ page }) => {
  const invalid = await page.request.get("http://127.0.0.1:42818/api/catalog?q=");
  expect(invalid.status()).toBe(422);
  expect((await invalid.json()).code).toBe("request_validation_failed");

  await page.goto("/");
  await page.getByLabel("종목명 또는 종목코드").fill("테스트기업");
  const catalogResponse = page.waitForResponse((response) => response.url().includes("/api/catalog"));
  await page.getByRole("button", { name: "검색", exact: true }).click();
  const catalogPayload = await catalogResponse;
  expect(catalogPayload.status()).toBe(200);
  expect(await catalogPayload.json()).toHaveLength(1);
  await expect(page.getByText("1개 종목을 찾았습니다.")).toBeVisible();
  await page.getByRole("button", { name: /테스트기업/ }).click();
  await page.getByLabel("시작").fill("2026-06-17T09:00");
  await page.getByLabel("종료").fill("2026-06-17T15:30");
  await page.getByRole("button", { name: "차트 불러오기" }).click();
  const chart = page.getByLabel("1분봉 차트");
  await expect(chart).toBeVisible();
  await chart.click({ position: { x: 300, y: 200 } });
  await expect(page.getByTestId("selected-candle")).toContainText("뉴스 검색 구간");

  const discoveryResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/news/discover") && response.status() === 200,
  );
  await page.getByRole("button", { name: "선택 구간 뉴스 검색" }).click();
  const discovery = await (await discoveryResponse).json();
  const sampleId = discovery.articles[0].sample_id as string;
  const initialHistoryResponse = await page.request.get(
    `http://127.0.0.1:42818/api/annotations/${sampleId}`,
  );
  const initialRevisionCount = (await initialHistoryResponse.json()).length as number;
  await expect(page.getByRole("heading", { name: "테스트기업 계약" })).toBeVisible();

  await page.getByRole("button", { name: "관련" }).click();
  await expect(page.getByText(`최종 relevant · rev ${initialRevisionCount + 1}`)).toBeVisible();
  await page.getByRole("button", { name: "불확실" }).click();
  await expect(page.getByText(`최종 uncertain · rev ${initialRevisionCount + 2}`)).toBeVisible();
  await page.getByRole("button", { name: "관련" }).click();
  await expect(page.getByText(`최종 relevant · rev ${initialRevisionCount + 3}`)).toBeVisible();

  const history = await page.request.get(
    `http://127.0.0.1:42818/api/annotations/${sampleId}`,
  );
  expect(history.status()).toBe(200);
  const revisions = (await history.json()).map((row: { revision: number }) => row.revision);
  expect(revisions.slice(-3)).toEqual([
    initialRevisionCount + 1,
    initialRevisionCount + 2,
    initialRevisionCount + 3,
  ]);

  const freezeResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/datasets") && response.status() === 200,
  );
  await page.getByRole("button", { name: "버전 스냅샷 고정" }).click();
  const frozen = await (await freezeResponse).json();
  expect(frozen.members[0].annotation.revision).toBe(initialRevisionCount + 3);
  expect(frozen.members[0].provenance.discovery_plan.calls.length).toBeGreaterThan(0);
  await expect(page.getByText(/고정하고 내보냈습니다/)).toBeVisible();
  await expect(page.getByText("db: succeeded")).toBeVisible();
  await expect(page.getByText("json: succeeded")).toBeVisible();
  await expect(page.getByText("csv: succeeded")).toBeVisible();
});
