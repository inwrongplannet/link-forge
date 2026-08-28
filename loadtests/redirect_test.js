import http from "k6/http";
import { check, fail, sleep } from "k6";

export const options = {
    stages: [
        { duration: "30s", target: 500 },
        { duration: "1m", target: 500 },
        { duration: "30s", target: 0 },
    ],
    thresholds: {
        http_req_duration: ["p(95)<100"],
        http_req_failed: ["rate<0.01"],
    },
};

export default function () {
    const shortCode = __ENV.SHORT_CODE;
    if (!shortCode) {
        fail("SHORT_CODE is required; run seed.py and pass its output with -e SHORT_CODE=<code>");
    }

    const res = http.get(`http://localhost:8080/${shortCode}`, { redirects: 0 });
    check(res, { "status is 302": (r) => r.status === 302 });
    sleep(0.1);
}
