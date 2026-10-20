// Entrar com digital ou rosto (passkeys, padrão WebAuthn).
// O navegador pede a digital, o rosto ou o PIN do próprio aparelho e assina um
// desafio do servidor. A biometria nunca sai do aparelho; o servidor só recebe a
// assinatura e guarda a chave pública.

import { api } from "./api";

export type PasskeyItem = { id: string; nome: string; criada_em: string; usada_em: string | null };
type Me = { id: string; usuario: string; nome: string };
type ChallengeOut<T> = { desafio_id: string; opcoes: T };
type Descriptor = { id: string; type: string; transports?: string[] };
// Opções no formato JSON que o servidor envia (binários em base64url).
type CreationJSON = {
  rp: PublicKeyCredentialRpEntity;
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: PublicKeyCredentialParameters[];
  timeout?: number;
  attestation?: AttestationConveyancePreference;
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  excludeCredentials?: Descriptor[];
};
type RequestJSON = {
  challenge: string;
  rpId?: string;
  timeout?: number;
  userVerification?: UserVerificationRequirement;
  allowCredentials?: Descriptor[];
};

/** Base64 sem preenchimento e seguro para URL (formato do WebAuthn em JSON). */
export function base64urlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const b64 = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function bytesToBase64url(data: ArrayBuffer | Uint8Array): string {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** Nome sugerido para o aparelho, só para a pessoa reconhecer na lista. */
export function guessDeviceName(userAgent: string): string {
  if (/iPhone/.test(userAgent)) return "iPhone";
  if (/iPad/.test(userAgent)) return "iPad";
  if (/Android/.test(userAgent)) return "Celular Android";
  if (/Macintosh/.test(userAgent)) return "Mac";
  if (/Windows/.test(userAgent)) return "Computador Windows";
  return "Este aparelho";
}

/** O aparelho tem sensor próprio (digital, rosto ou PIN) que o navegador pode usar? */
export async function passkeySupported(): Promise<boolean> {
  if (typeof window === "undefined" || typeof window.PublicKeyCredential === "undefined") return false;
  try {
    return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** Mensagem compreensível para as falhas do próprio aparelho. */
export function passkeyErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "AbortError") return "Cancelado ou o tempo acabou. Tente de novo.";
  if (name === "InvalidStateError") return "Este aparelho já está ativado.";
  if (name === "SecurityError") return "Este endereço não permite usar digital ou rosto.";
  if (err instanceof Error && !(err instanceof DOMException)) return err.message;
  return "Este aparelho não conseguiu usar a digital ou o rosto. Use usuário e senha.";
}

const descriptors = (list: Descriptor[] | undefined): PublicKeyCredentialDescriptor[] =>
  (list ?? []).map((c) => ({
    type: "public-key",
    id: base64urlToBytes(c.id),
    transports: c.transports as AuthenticatorTransport[] | undefined,
  }));

export async function activatePasskey(deviceName: string): Promise<PasskeyItem> {
  const ch = await api.post<ChallengeOut<CreationJSON>>("/auth/digital/cadastro/opcoes");
  const o = ch.opcoes;
  const publicKey: PublicKeyCredentialCreationOptions = {
    rp: o.rp,
    user: { ...o.user, id: base64urlToBytes(o.user.id) },
    challenge: base64urlToBytes(o.challenge),
    pubKeyCredParams: o.pubKeyCredParams,
    timeout: o.timeout,
    attestation: o.attestation,
    authenticatorSelection: o.authenticatorSelection,
    excludeCredentials: descriptors(o.excludeCredentials),
  };
  const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
  if (!cred) throw new DOMException("cancelado", "NotAllowedError");
  const r = cred.response as AuthenticatorAttestationResponse;
  return api.post<PasskeyItem>("/auth/digital/cadastro", {
    desafio_id: ch.desafio_id,
    nome_aparelho: deviceName,
    credencial: {
      id: cred.id,
      rawId: bytesToBase64url(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
      clientExtensionResults: {},
      response: {
        clientDataJSON: bytesToBase64url(r.clientDataJSON),
        attestationObject: bytesToBase64url(r.attestationObject),
        transports: typeof r.getTransports === "function" ? r.getTransports() : [],
      },
    },
  });
}

export async function loginWithPasskey(remember: boolean): Promise<Me> {
  const ch = await api.post<ChallengeOut<RequestJSON>>("/auth/digital/entrar/opcoes");
  const o = ch.opcoes;
  const publicKey: PublicKeyCredentialRequestOptions = {
    challenge: base64urlToBytes(o.challenge),
    rpId: o.rpId,
    timeout: o.timeout,
    userVerification: o.userVerification,
    allowCredentials: descriptors(o.allowCredentials),
  };
  const cred = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
  if (!cred) throw new DOMException("cancelado", "NotAllowedError");
  const r = cred.response as AuthenticatorAssertionResponse;
  return api.post<Me>("/auth/digital/entrar", {
    desafio_id: ch.desafio_id,
    manter_conectado: remember,
    credencial: {
      id: cred.id,
      rawId: bytesToBase64url(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
      clientExtensionResults: {},
      response: {
        clientDataJSON: bytesToBase64url(r.clientDataJSON),
        authenticatorData: bytesToBase64url(r.authenticatorData),
        signature: bytesToBase64url(r.signature),
        ...(r.userHandle ? { userHandle: bytesToBase64url(r.userHandle) } : {}),
      },
    },
  });
}
