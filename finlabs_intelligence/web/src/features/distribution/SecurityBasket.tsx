import type { CatalogItemResponse } from "../../shared/api";
import { securityColor } from "./useDistribution";

interface SecurityBasketProps {
  readonly basket: readonly CatalogItemResponse[];
  readonly activeId: string | null;
  readonly onActivate: (securityId: string) => void;
  readonly onRemove: (securityId: string) => void;
}

// The set of securities under analysis, built by repeatedly searching and
// adding. The active chip drives the left chart (and its drag window); every
// loaded security still contributes to the distribution on the right.
export function SecurityBasket({
  basket,
  activeId,
  onActivate,
  onRemove,
}: SecurityBasketProps) {
  return (
    <div className={basket.length ? "bridge basket active" : "bridge basket"} aria-label="분석 종목">
      <span className="bridge-label">분석 종목</span>
      {basket.length === 0 ? (
        <span className="bridge-empty">검색해서 종목을 추가하세요.</span>
      ) : (
        <ul className="basket-chips">
          {basket.map((item, index) => (
            <li key={item.security_id}>
              <span className={item.security_id === activeId ? "basket-chip active" : "basket-chip"}>
                <button
                  aria-label={`${item.display_name} 차트 보기`}
                  aria-pressed={item.security_id === activeId}
                  className="basket-chip-select"
                  onClick={() => onActivate(item.security_id)}
                  type="button"
                >
                  <span className="basket-dot" style={{ background: securityColor(index) }} />
                  <strong>{item.display_name}</strong>
                  <span className="basket-symbol">{item.symbol}</span>
                </button>
                <button
                  aria-label={`${item.display_name} 제거`}
                  className="basket-chip-remove"
                  onClick={() => onRemove(item.security_id)}
                  type="button"
                >×</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
