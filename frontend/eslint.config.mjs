import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "out/**", "next-env.d.ts"] },
  {
    rules: {
      // Datas civis trafegam como texto AAAA-MM-DD. new Date("2026-10-15") é lido
      // como meia-noite UTC e aparece como 14/10 no Brasil.
      "no-restricted-syntax": [
        "error",
        {
          selector: "NewExpression[callee.name='Date'][arguments.length=1]",
          message: "Não use new Date(valor): use as funções de src/lib/format.ts para datas civis.",
        },
        {
          selector: "CallExpression[callee.object.name='Date'][callee.property.name='parse']",
          message: "Não use Date.parse: use as funções de src/lib/format.ts.",
        },
        {
          selector: "CallExpression[callee.name='parseFloat']",
          message: "Não use parseFloat em valores: dinheiro é inteiro em centavos.",
        },
      ],
    },
  },
];

export default config;
