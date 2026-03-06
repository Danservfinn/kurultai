/**
 * Parse x402 Payment Validation
 * Additional validation utilities for x402 payments
 * 
 * Complements payment.ts with focused validation logic
 */

import { X402PaymentProof, X402Config, X402ValidationResult } from './payment'

/**
 * Payment validation cache
 * Prevents replay attacks by tracking recently used payment IDs
 */
const REPLAY_CACHE = new Map<string, number>()
const CACHE_TTL_MS = 300_000 // 5 minutes

/**
 * Clean expired entries from replay cache
 */
function cleanReplayCache() {
  const now = Date.now()
  for (const [paymentId, timestamp] of REPLAY_CACHE.entries()) {
    if (now - timestamp > CACHE_TTL_MS) {
      REPLAY_CACHE.delete(paymentId)
    }
  }
}

/**
 * Check if payment has already been used (replay attack prevention)
 * 
 * @param paymentId - Unique payment identifier
 * @returns True if payment was already used
 */
export function isReplayAttack(paymentId: string): boolean {
  cleanReplayCache()
  
  if (REPLAY_CACHE.has(paymentId)) {
    return true
  }
  
  // Mark as used
  REPLAY_CACHE.set(paymentId, Date.now())
  return false
}

/**
 * Validate payment amount against expected pricing
 * 
 * @param amount - Amount from payment proof
 * @param expectedAmount - Expected amount in cents
 * @param tolerance - Allowed tolerance in cents (default: 0)
 * @returns Validation result
 */
export function validatePaymentAmount(
  amount: number,
  expectedAmount: number,
  tolerance: number = 0
): { valid: boolean; reason?: string } {
  if (amount < expectedAmount - tolerance) {
    return {
      valid: false,
      reason: `Insufficient payment: expected ${expectedAmount} cents, got ${amount} cents`,
    }
  }
  
  if (amount > expectedAmount + tolerance) {
    return {
      valid: false,
      reason: `Overpayment: expected ${expectedAmount} cents, got ${amount} cents`,
    }
  }
  
  return { valid: true }
}

/**
 * Validate payment currency
 * 
 * @param currency - Currency from payment proof
 * @param acceptedCurrencies - List of accepted currencies
 * @returns Validation result
 */
export function validatePaymentCurrency(
  currency: string,
  acceptedCurrencies: string[] = ['USD', 'BTC', 'ETH']
): { valid: boolean; reason?: string } {
  if (!acceptedCurrencies.includes(currency)) {
    return {
      valid: false,
      reason: `Unsupported currency: ${currency}. Accepted: ${acceptedCurrencies.join(', ')}`,
    }
  }
  
  return { valid: true }
}

/**
 * Validate payment timestamp (not expired, not in future)
 * 
 * @param timestamp - Unix timestamp from payment proof
 * @param maxAge - Maximum age in seconds (default: 300 = 5 minutes)
 * @returns Validation result
 */
export function validatePaymentTimestamp(
  timestamp: number,
  maxAge: number = 300
): { valid: boolean; reason?: string } {
  const now = Math.floor(Date.now() / 1000)
  const age = now - timestamp
  
  // Check if payment is from the future
  if (timestamp > now + 60) {
    return {
      valid: false,
      reason: 'Payment timestamp is in the future',
    }
  }
  
  // Check if payment is expired
  if (age > maxAge) {
    return {
      valid: false,
      reason: `Payment expired (${age} seconds old, max ${maxAge} seconds)`,
    }
  }
  
  return { valid: true }
}

/**
 * Validate wallet address format
 * 
 * @param address - Wallet address to validate
 * @param addressType - Type of address (email-style, crypto, etc.)
 * @returns Validation result
 */
export function validateWalletAddress(
  address: string,
  addressType: 'email' | 'crypto' | 'did' = 'email'
): { valid: boolean; reason?: string } {
  if (!address || address.trim() === '') {
    return {
      valid: false,
      reason: 'Wallet address is empty',
    }
  }
  
  switch (addressType) {
    case 'email':
      // Email-style address: parse@kurult.ai
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (!emailRegex.test(address)) {
        return {
          valid: false,
          reason: 'Invalid email-style wallet address format',
        }
      }
      break
    
    case 'crypto':
      // Crypto address (simplified check)
      if (address.length < 26 || address.length > 62) {
        return {
          valid: false,
          reason: 'Invalid crypto wallet address length',
        }
      }
      break
    
    case 'did':
      // DID format: did:method:identifier
      if (!address.startsWith('did:')) {
        return {
          valid: false,
          reason: 'Invalid DID format (should start with "did:")',
        }
      }
      break
  }
  
  return { valid: true }
}

/**
 * Comprehensive payment validation
 * 
 * Combines all validation checks into a single function
 * 
 * @param proof - Payment proof to validate
 * @param config - Expected payment configuration
 * @returns Detailed validation result
 */
export function validatePaymentComprehensive(
  proof: X402PaymentProof,
  config: X402Config
): X402ValidationResult {
  // Check for replay attack
  if (isReplayAttack(proof.paymentId)) {
    return {
      valid: false,
      reason: 'Payment already used (replay attack detected)',
    }
  }
  
  // Validate payee
  if (proof.payee !== config.payTo) {
    return {
      valid: false,
      reason: `Invalid payee: expected ${config.payTo}, got ${proof.payee}`,
    }
  }
  
  // Validate amount
  const amountValidation = validatePaymentAmount(proof.amount, config.amount)
  if (!amountValidation.valid) {
    return amountValidation
  }
  
  // Validate currency
  const currencyValidation = validatePaymentCurrency(proof.currency, [config.currency])
  if (!currencyValidation.valid) {
    return currencyValidation
  }
  
  // Validate timestamp
  const timestampValidation = validatePaymentTimestamp(proof.timestamp, config.expiresInSeconds)
  if (!timestampValidation.valid) {
    return timestampValidation
  }
  
  // Validate wallet addresses
  const payerValidation = validateWalletAddress(proof.payer, 'email')
  if (!payerValidation.valid) {
    return payerValidation
  }
  
  const payeeValidation = validateWalletAddress(proof.payee, 'email')
  if (!payeeValidation.valid) {
    return payeeValidation
  }
  
  // All validations passed
  return {
    valid: true,
    proof,
  }
}

/**
 * Validate payment signature structure
 * 
 * Checks that signature is present and properly formatted
 * Does NOT perform cryptographic verification (see verifyX402Signature in payment.ts)
 * 
 * @param signature - Signature string to validate
 * @returns Validation result
 */
export function validateSignatureStructure(signature: string): { valid: boolean; reason?: string } {
  if (!signature || signature.trim() === '') {
    return {
      valid: false,
      reason: 'Signature is missing',
    }
  }
  
  // Signature should be at least 64 characters (typical for cryptographic signatures)
  if (signature.length < 64) {
    return {
      valid: false,
      reason: 'Signature too short (possible invalid format)',
    }
  }
  
  // Signature should be hexadecimal or base64
  const hexPattern = /^[0-9a-fA-F]+$/
  const base64Pattern = /^[A-Za-z0-9+/=]+$/
  
  if (!hexPattern.test(signature) && !base64Pattern.test(signature)) {
    return {
      valid: false,
      reason: 'Signature format invalid (should be hex or base64)',
    }
  }
  
  return { valid: true }
}

/**
 * Get validation error code for programmatic handling
 * 
 * @param reason - Validation failure reason
 * @returns Error code
 */
export function getValidationErrorCode(reason: string): string {
  if (reason.includes('payee')) return 'X402_INVALID_PAYEE'
  if (reason.includes('amount')) return 'X402_INVALID_AMOUNT'
  if (reason.includes('currency')) return 'X402_INVALID_CURRENCY'
  if (reason.includes('expired')) return 'X402_PAYMENT_EXPIRED'
  if (reason.includes('signature')) return 'X402_INVALID_SIGNATURE'
  if (reason.includes('replay')) return 'X402_REPLAY_ATTACK'
  if (reason.includes('timestamp')) return 'X402_INVALID_TIMESTAMP'
  if (reason.includes('address')) return 'X402_INVALID_ADDRESS'
  if (reason.includes('format')) return 'X402_INVALID_FORMAT'
  
  return 'X402_VALIDATION_ERROR'
}
