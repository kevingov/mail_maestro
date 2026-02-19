# Cohort Tracking & A/B Testing Setup Guide

## 🎯 Overview

Your Mail Maestro app now has comprehensive cohort tracking and A/B testing capabilities for clean ramp-up management (20-50 merchants initially, scaling to full rollout).

---

## 📊 What Was Added

### Database Schema
✅ **email_tracking table** - Added columns:
- `merchant_id` - Unique merchant identifier (SFDC ID)
- `cohort_name` - Cohort identifier (e.g., "pilot_batch1")
- `cohort_batch` - Numeric batch number (1, 2, 3...)
- `test_group` - Test assignment ("control", "variant_a", "variant_b")
- `ramp_phase` - Phase ("pilot", "ramp_up", "full_rollout")
- `enrolled_at` - When merchant was enrolled

✅ **merchant_cohorts table** - New table:
- Tracks which merchants are in which cohorts
- Maintains test group assignments
- Status tracking (active/paused/completed)

### API Updates
✅ **send-new-email endpoint** - Now accepts cohort data
✅ **Dynamic campaign names** - No longer hardcoded
✅ **Analytics endpoints** - 3 new reporting endpoints

---

## 🔧 Step 1: Update Workato Configuration

### Required Fields to Send

Update your Workato recipe to send these additional fields when calling `/api/workato/send-new-email`:

```json
{
  // Existing fields
  "contact_email": "merchant@example.com",
  "contact_name": "John Doe",
  "account_name": "Acme Corp",
  "account_id": "SFDC_12345",

  // NEW COHORT FIELDS - Add these
  "merchant_id": "SFDC_12345",           // Use SFDC Account ID
  "cohort_name": "pilot_batch1",         // Your cohort identifier
  "cohort_batch": 1,                     // Batch number (1, 2, 3...)
  "test_group": "control",               // "control", "variant_a", or "variant_b"
  "ramp_phase": "pilot",                 // "pilot", "ramp_up", or "full_rollout"
  "campaign_name": "pilot_batch1_control_2026-02"  // Optional - will auto-generate if not provided
}
```

### Recommended Workato Setup

#### For Pilot (Batch 1 - 20 merchants):
```json
{
  "merchant_id": "{{account_id}}",
  "cohort_name": "pilot_batch1",
  "cohort_batch": 1,
  "test_group": "control",
  "ramp_phase": "pilot",
  "campaign_name": "pilot_batch1_control_2026-02"
}
```

#### For Ramp-Up (Batch 2 - 30 merchants with A/B test):
**Control group (15 merchants):**
```json
{
  "merchant_id": "{{account_id}}",
  "cohort_name": "rampup_batch2",
  "cohort_batch": 2,
  "test_group": "control",
  "ramp_phase": "ramp_up",
  "campaign_name": "rampup_batch2_control_2026-02"
}
```

**Variant A (15 merchants):**
```json
{
  "merchant_id": "{{account_id}}",
  "cohort_name": "rampup_batch2",
  "cohort_batch": 2,
  "test_group": "variant_a",
  "ramp_phase": "ramp_up",
  "campaign_name": "rampup_batch2_variantA_2026-02"
}
```

### How to Assign Test Groups in Workato

**Option 1: Manual Assignment (Recommended for Pilot)**
- Create separate lists/views in SFDC for each test group
- Use Workato filters to route to appropriate group

**Option 2: Automatic Random Assignment**
- Use Workato formula: `{{account_id % 2 == 0 ? "control" : "variant_a"}}`
- This splits 50/50 based on account ID

**Option 3: Pre-assigned in SFDC**
- Create a custom field in SFDC: `Test_Group__c`
- Set it before the Workato recipe runs
- Use: `{{test_group__c}}`

---

## 🧪 Step 2: Test the Implementation

### Test 1: Send Test Email with Cohort Data

Use curl or Postman:

```bash
curl -X POST https://web-production-6dfbd.up.railway.app/api/workato/send-new-email \
  -H "Content-Type: application/json" \
  -d '{
    "contact_email": "your-test-email@example.com",
    "contact_name": "Test Merchant",
    "account_name": "Test Account",
    "account_id": "TEST_001",
    "merchant_id": "TEST_001",
    "cohort_name": "test_cohort",
    "cohort_batch": 0,
    "test_group": "control",
    "ramp_phase": "pilot",
    "campaign_name": "test_campaign"
  }'
```

**Expected response:**
```json
{
  "status": "success",
  "message": "Personalized email sent successfully",
  "tracking_id": "uuid-here",
  "tracking_url": "https://web-production-6dfbd.up.railway.app/track/uuid",
  "campaign": "test_campaign"
}
```

### Test 2: Verify Database Storage

Check the cohort was stored:

```bash
curl https://web-production-6dfbd.up.railway.app/api/analytics/cohort-performance
```

**Expected response:**
```json
{
  "status": "success",
  "cohorts": [
    {
      "cohort_name": "test_cohort",
      "cohort_batch": 0,
      "test_group": "control",
      "ramp_phase": "pilot",
      "emails_sent": 1,
      "emails_opened": 0,
      "open_rate": 0.0
    }
  ]
}
```

---

## 📈 Step 3: Monitor Analytics

### Analytics Endpoints

#### 1. Cohort Performance
**GET** `/api/analytics/cohort-performance`

Shows performance by cohort:
```bash
curl https://web-production-6dfbd.up.railway.app/api/analytics/cohort-performance
```

**Response:**
```json
{
  "status": "success",
  "cohorts": [
    {
      "cohort_name": "pilot_batch1",
      "cohort_batch": 1,
      "test_group": "control",
      "ramp_phase": "pilot",
      "emails_sent": 20,
      "emails_opened": 8,
      "open_rate": 40.0,
      "avg_opens_per_email": 1.2,
      "first_email_sent": "2026-02-17T10:00:00",
      "last_email_sent": "2026-02-17T14:30:00"
    }
  ]
}
```

#### 2. A/B Test Results
**GET** `/api/analytics/ab-test-results`

Compare test groups:
```bash
curl https://web-production-6dfbd.up.railway.app/api/analytics/ab-test-results

# Filter specific groups
curl "https://web-production-6dfbd.up.railway.app/api/analytics/ab-test-results?test_groups=control,variant_a"
```

**Response:**
```json
{
  "status": "success",
  "test_results": [
    {
      "test_group": "control",
      "emails_sent": 15,
      "emails_opened": 6,
      "open_rate": 40.0,
      "unique_merchants": 15
    },
    {
      "test_group": "variant_a",
      "emails_sent": 15,
      "emails_opened": 9,
      "open_rate": 60.0,
      "unique_merchants": 15,
      "vs_control": {
        "open_rate_diff": 20.0,
        "open_rate_lift_pct": 50.0
      }
    }
  ]
}
```

#### 3. Ramp Dashboard
**GET** `/api/analytics/ramp-dashboard`

Overall metrics:
```bash
curl https://web-production-6dfbd.up.railway.app/api/analytics/ramp-dashboard
```

**Response:**
```json
{
  "status": "success",
  "overall": {
    "total_emails": 50,
    "total_opens": 20,
    "overall_open_rate": 40.0,
    "unique_merchants": 50,
    "total_cohorts": 3
  },
  "by_phase": [
    {
      "ramp_phase": "pilot",
      "emails_sent": 20,
      "emails_opened": 8,
      "open_rate": 40.0,
      "unique_merchants": 20
    }
  ],
  "cohort_summary": [
    {
      "cohort_name": "pilot_batch1",
      "merchant_count": 20,
      "status": "active"
    }
  ]
}
```

---

## 🚀 Step 4: Pilot Rollout Plan

### Week 1: Pilot Batch 1 (20 merchants)

**Setup:**
```json
{
  "cohort_name": "pilot_batch1",
  "cohort_batch": 1,
  "test_group": "control",
  "ramp_phase": "pilot"
}
```

**Goals:**
- ✅ Validate tracking is working
- ✅ Measure baseline open rates
- ✅ Ensure campaign_name is correct
- ✅ Verify merchant_cohorts table is populated

**Monitor:** `/api/analytics/ramp-dashboard`

### Week 2-3: Ramp-Up Batch 2 (30 merchants)

**A/B Test Setup:**

Split into 2 groups (15 control, 15 variant_a):

**Control:**
```json
{
  "cohort_name": "rampup_batch2",
  "cohort_batch": 2,
  "test_group": "control",
  "ramp_phase": "ramp_up",
  "version_endpoint": "/api/workato/send-new-email"
}
```

**Variant A (test new prompt):**
```json
{
  "cohort_name": "rampup_batch2",
  "cohort_batch": 2,
  "test_group": "variant_a",
  "ramp_phase": "ramp_up",
  "version_endpoint": "/api/workato/send-new-email-version-A"
}
```

**Monitor:** `/api/analytics/ab-test-results?test_groups=control,variant_a`

**Decision Criteria:**
- If variant_a shows >20% lift in open rate → Roll out to batch 3
- If variant_a shows <10% lift → Stick with control

### Week 4+: Full Rollout

Scale to remaining merchants using winning variant.

---

## 🔍 Troubleshooting

### Issue: Cohort data not showing in analytics

**Check 1:** Verify fields are being sent from Workato
```bash
# Look at recent email_tracking records
curl https://web-production-6dfbd.up.railway.app/api/emails?limit=10
```

**Check 2:** Ensure merchant_id is not null
- merchant_id is required for merchant_cohorts table
- Falls back to account_id if not provided

### Issue: Campaign name is still "MSS Signed But Not Activated Campaign"

**Solution:** Make sure you're sending `campaign_name` in the request body. If not sent, it will auto-generate from cohort data, or fall back to default.

### Issue: Analytics showing 0 emails

**Check:** Database was just updated - wait for Railway to restart
- Railway auto-deploys when you push to main
- Takes ~2-3 minutes
- Check Railway logs for "✅ PostgreSQL database initialized"

---

## 📋 Quick Reference: Field Guide

| Field | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| `merchant_id` | String | Yes | "SFDC_12345" | Primary key for cohort tracking |
| `cohort_name` | String | Yes | "pilot_batch1" | Human-readable cohort identifier |
| `cohort_batch` | Integer | Yes | 1 | Numeric batch (1, 2, 3...) |
| `test_group` | String | Yes | "control" | control, variant_a, variant_b |
| `ramp_phase` | String | Yes | "pilot" | pilot, ramp_up, full_rollout |
| `campaign_name` | String | No | "pilot_batch1_control_2026-02" | Auto-generated if not provided |
| `enrolled_at` | Timestamp | No | "2026-02-17T10:00:00Z" | Defaults to now |

---

## ✅ Next Steps

1. **Update Workato** - Add cohort fields to request body
2. **Test with 1 email** - Verify tracking works
3. **Check analytics** - Confirm data appears in endpoints
4. **Pilot with 20 merchants** - Start batch 1
5. **Monitor for 1 week** - Review open rates
6. **Plan A/B test** - Set up batch 2 with variants
7. **Scale up** - Roll out winning variant

---

## 🆘 Need Help?

- Check Railway logs: https://railway.app
- Test endpoints: Use curl commands above
- Database issues: Restart Railway service
- Workato issues: Check recipe execution logs

**The system is now live and ready for your pilot! 🚀**
