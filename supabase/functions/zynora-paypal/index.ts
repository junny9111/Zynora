import { createClient } from "jsr:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(data: any, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}

/* ============================================================
   ZYNORA COIN PACKAGES
   THESE PRICES ARE SERVER CONTROLLED
============================================================ */

const PACKAGES: Record<
  string,
  {
    name: string;
    coins: number;
    amount: string;
  }
> = {
  coins_250: {
    name: "250 Zynora Coins",
    coins: 250,
    amount: "4.99",
  },

  coins_500: {
    name: "500 Zynora Coins",
    coins: 500,
    amount: "9.99",
  },

  coins_1200: {
    name: "1,200 Zynora Coins",
    coins: 1200,
    amount: "19.99",
  },

  coins_3000: {
    name: "3,000 Zynora Coins",
    coins: 3000,
    amount: "29.99",
  },
};

/* ============================================================
   PAYPAL SETTINGS
============================================================ */

function paypalBaseUrl() {
  const env =
    (Deno.env.get("PAYPAL_ENV") || "sandbox").toLowerCase();

  return env === "live"
    ? "https://api-m.paypal.com"
    : "https://api-m.sandbox.paypal.com";
}

async function getPayPalAccessToken() {
  const clientId =
    Deno.env.get("PAYPAL_CLIENT_ID");

  const clientSecret =
    Deno.env.get("PAYPAL_CLIENT_SECRET");

  if (!clientId || !clientSecret) {
    throw new Error(
      "PayPal credentials are not configured."
    );
  }

  const basicAuth =
    btoa(`${clientId}:${clientSecret}`);

  const response =
    await fetch(
      `${paypalBaseUrl()}/v1/oauth2/token`,
      {
        method: "POST",

        headers: {
          Authorization:
            `Basic ${basicAuth}`,

          "Content-Type":
            "application/x-www-form-urlencoded",
        },

        body:
          "grant_type=client_credentials",
      }
    );

  const data =
    await response.json();

  if (!response.ok) {
    console.error(
      "PayPal access token error:",
      data
    );

    throw new Error(
      "Unable to authenticate with PayPal."
    );
  }

  return data.access_token;
}

/* ============================================================
   SUPABASE ADMIN
============================================================ */

const supabaseUrl =
  Deno.env.get("SUPABASE_URL");

const serviceRoleKey =
  Deno.env.get(
    "SUPABASE_SERVICE_ROLE_KEY"
  );

if (!supabaseUrl || !serviceRoleKey) {
  throw new Error(
    "Supabase server credentials are missing."
  );
}

const supabaseAdmin =
  createClient(
    supabaseUrl,
    serviceRoleKey,
    {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    }
  );

/* ============================================================
   GET LOGGED-IN ZYNORA USER
============================================================ */

async function getAuthenticatedUser(
  request: Request
) {
  const authHeader =
    request.headers.get("Authorization");

  if (
    !authHeader ||
    !authHeader.startsWith("Bearer ")
  ) {
    throw new Error(
      "AUTH_REQUIRED"
    );
  }

  const token =
    authHeader.replace(
      "Bearer ",
      ""
    );

  const {
    data,
    error,
  } =
    await supabaseAdmin.auth.getUser(
      token
    );

  if (
    error ||
    !data?.user
  ) {
    console.error(
      "Supabase auth error:",
      error
    );

    throw new Error(
      "INVALID_SESSION"
    );
  }

  return data.user;
}

/* ============================================================
   MAIN EDGE FUNCTION
============================================================ */

Deno.serve(
  async (request: Request) => {
    if (
      request.method === "OPTIONS"
    ) {
      return new Response(
        "ok",
        {
          headers:
            corsHeaders,
        }
      );
    }

    if (
      request.method !== "POST"
    ) {
      return jsonResponse(
        {
          error:
            "Method not allowed.",
        },
        405
      );
    }

    try {
      /* ======================================================
         REQUIRE A REAL LOGGED-IN ZYNORA USER
      ====================================================== */

      let user;

      try {
        user =
          await getAuthenticatedUser(
            request
          );
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "";

        if (
          message ===
            "AUTH_REQUIRED" ||
          message ===
            "INVALID_SESSION"
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "Please log in to Zynora before making a purchase.",
            },
            401
          );
        }

        throw error;
      }

      const body =
        await request.json();

      const action =
        body?.action;

      /* ======================================================
         CREATE PAYPAL ORDER
      ====================================================== */

      if (
        action ===
        "create-order"
      ) {
        const packageId =
          body?.packageId;

        const selected =
          PACKAGES[
            packageId
          ];

        if (!selected) {
          return jsonResponse(
            {
              success: false,
              error:
                "Invalid Zynora coin package.",
            },
            400
          );
        }

        const accessToken =
          await getPayPalAccessToken();

        const returnUrl =
          "https://junny9111.github.io/Zynora/payment-success.html";

        const cancelUrl =
          "https://junny9111.github.io/Zynora/buy-coins.html?cancelled=1";

        const paypalResponse =
          await fetch(
            `${paypalBaseUrl()}/v2/checkout/orders`,
            {
              method: "POST",

              headers: {
                Authorization:
                  `Bearer ${accessToken}`,

                "Content-Type":
                  "application/json",

                "PayPal-Request-Id":
                  crypto.randomUUID(),

                Prefer:
                  "return=representation",
              },

              body:
                JSON.stringify(
                  {
                    intent:
                      "CAPTURE",

                    purchase_units:
                      [
                        {
                          reference_id:
                            packageId,

                          custom_id:
                            user.id,

                          description:
                            selected.name,

                          amount:
                            {
                              currency_code:
                                "USD",

                              value:
                                selected.amount,
                            },
                        },
                      ],

                    payment_source:
                      {
                        paypal:
                          {
                            experience_context:
                              {
                                brand_name:
                                  "Zynora",

                                landing_page:
                                  "LOGIN",

                                user_action:
                                  "PAY_NOW",

                                return_url:
                                  returnUrl,

                                cancel_url:
                                  cancelUrl,
                              },
                          },
                      },
                  }
                ),
            }
          );

        const data =
          await paypalResponse.json();

        if (
          !paypalResponse.ok
        ) {
          console.error(
            "PayPal create order error:",
            data
          );

          return jsonResponse(
            {
              success: false,

              error:
                "PayPal could not create the order.",

              paypal:
                data,
            },
            paypalResponse.status
          );
        }

        const approvalLink =
          data?.links?.find(
            (link: any) =>
              link.rel ===
              "payer-action"
          )?.href ||
          data?.links?.find(
            (link: any) =>
              link.rel ===
              "approve"
          )?.href ||
          null;

        return jsonResponse(
          {
            success: true,

            orderId:
              data.id,

            status:
              data.status,

            packageId,

            amount:
              selected.amount,

            coins:
              selected.coins,

            approvalUrl:
              approvalLink,
          }
        );
      }

      /* ======================================================
         CAPTURE PAYPAL ORDER
         + VERIFY
         + CREDIT REAL ZYNORA WALLET
      ====================================================== */

      if (
        action ===
        "capture-order"
      ) {
        const orderId =
          body?.orderId;

        if (
          !orderId ||
          typeof orderId !==
            "string"
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal order ID is required.",
            },
            400
          );
        }

        const accessToken =
          await getPayPalAccessToken();


        // Verify ownership and package before causing a payment capture.
        const lookup = await fetch(
          `${paypalBaseUrl()}/v2/checkout/orders/${encodeURIComponent(orderId)}`,
          { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        const existingOrder = await lookup.json();
        if (!lookup.ok) return jsonResponse({success:false,error:"Unable to look up this PayPal order."},lookup.status);
        const initialUnit=existingOrder?.purchase_units?.[0];
        const initialPackage=PACKAGES[initialUnit?.reference_id];
        if(initialUnit?.custom_id!==user.id) return jsonResponse({success:false,error:"This PayPal order does not belong to this Zynora account."},403);
        if(!initialPackage || initialUnit?.amount?.value!==initialPackage.amount || initialUnit?.amount?.currency_code!=="USD"){
          return jsonResponse({success:false,error:"PayPal order does not match a Zynora package."},400);
        }
        let data=existingOrder;
        if(existingOrder.status!=="COMPLETED"){
          const paypalResponse = await fetch(
            `${paypalBaseUrl()}/v2/checkout/orders/${encodeURIComponent(orderId)}/capture`,
            {
              method:"POST",
              headers:{
                Authorization:`Bearer ${accessToken}`,
                "Content-Type":"application/json",
                "PayPal-Request-Id":"zynora-capture-"+orderId,
                Prefer:"return=representation"
              },
              body:"{}"
            }
          );
          data=await paypalResponse.json();
          if(!paypalResponse.ok) return jsonResponse({success:false,error:"PayPal capture failed."},paypalResponse.status);
        }

        /* ====================================================
           PAYPAL MUST REPORT COMPLETED
        ==================================================== */

        if (
          data.status !==
          "COMPLETED"
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal payment has not completed.",

              status:
                data.status,
            },
            400
          );
        }

        const purchaseUnit =
          data
            ?.purchase_units
            ?.[0];

        const packageId =
          purchaseUnit
            ?.reference_id;

        const paypalUserId =
          purchaseUnit
            ?.custom_id;

        const capture =
          purchaseUnit
            ?.payments
            ?.captures
            ?.[0];

        if (
          !packageId
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal package reference is missing.",
            },
            400
          );
        }

        const selected =
          PACKAGES[
            packageId
          ];

        if (!selected) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal returned an unknown Zynora package.",
            },
            400
          );
        }

        /* ====================================================
           MAKE SURE ORDER BELONGS TO THIS ZYNORA USER
        ==================================================== */

        if (
          !paypalUserId ||
          paypalUserId !==
            user.id
        ) {
          console.error(
            "PayPal user mismatch",
            {
              authenticatedUser:
                user.id,

              paypalUser:
                paypalUserId,
            }
          );

          return jsonResponse(
            {
              success: false,

              error:
                "This PayPal order does not belong to the logged-in Zynora account.",
            },
            403
          );
        }

        /* ====================================================
           VERIFY CAPTURE
        ==================================================== */

        if (
          !capture ||
          capture.status !==
            "COMPLETED"
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal capture is not completed.",
            },
            400
          );
        }

        const captureId =
          capture.id;

        const capturedAmount =
          capture
            ?.amount
            ?.value;

        const currency =
          capture
            ?.amount
            ?.currency_code;

        if (!captureId) {
          return jsonResponse(
            {
              success: false,

              error:
                "PayPal capture ID is missing.",
            },
            400
          );
        }

        /* ====================================================
           VERIFY PRICE SERVER-SIDE
        ==================================================== */

        if (
          capturedAmount !==
          selected.amount
        ) {
          console.error(
            "PayPal amount mismatch:",
            {
              expected:
                selected.amount,

              received:
                capturedAmount,
            }
          );

          return jsonResponse(
            {
              success: false,

              error:
                "PayPal payment amount does not match the Zynora package.",
            },
            400
          );
        }

        if (
          currency !==
          "USD"
        ) {
          return jsonResponse(
            {
              success: false,

              error:
                "Unexpected PayPal currency.",
            },
            400
          );
        }

        /* ====================================================
           CREDIT ZYNORA WALLET

           The SQL function prevents duplicate captures
           from adding coins twice.
        ==================================================== */

        const {
          data:
            creditResult,

          error:
            creditError,
        } =
          await supabaseAdmin.rpc(
            "credit_paypal_purchase",
            {
              p_user_id:
                user.id,

              p_package_id:
                packageId,

              p_coins:
                selected.coins,

              p_amount_usd:
                capturedAmount,

              p_currency:
                currency,

              p_paypal_order_id:
                data.id,

              p_paypal_capture_id:
                captureId,
            }
          );

        if (creditError) {
          console.error(
            "Wallet credit error:",
            creditError
          );

          return jsonResponse(
            {
              success: false,

              error:
                "Payment succeeded, but Zynora could not update the wallet.",

              captureId,
            },
            500
          );
        }


        // Only verified live-payment proceeds receive a cash value.
        // Coin crediting remains idempotent even when fee reconciliation is delayed.
        let revenueReconciled = false;
        const livePayment = (Deno.env.get("PAYPAL_ENV") || "sandbox").toLowerCase() === "live";
        try {
          let receipt = capture;
          if (livePayment && !receipt.seller_receivable_breakdown?.net_amount) {
            const details = await fetch(
              `${paypalBaseUrl()}/v2/payments/captures/${encodeURIComponent(captureId)}`,
              { headers: { Authorization: `Bearer ${accessToken}` } }
            );
            if (details.ok) receipt = await details.json();
          }
          const net = receipt.seller_receivable_breakdown?.net_amount;
          const verifiedNet = livePayment ? (
            receipt.id === captureId && receipt.status === "COMPLETED" &&
            net?.currency_code === "USD" && Number.isFinite(Number(net.value)) &&
            Number(net.value) >= 0 && Number(net.value) <= Number(capturedAmount)
              ? Number(net.value) : null
          ) : 0;
          if (verifiedNet !== null) {
            const reconciled = await supabaseAdmin.from("paypal_purchases")
              .update({ net_amount_usd: verifiedNet })
              .eq("paypal_capture_id", captureId).eq("user_id", user.id)
              .select("id").single();
            revenueReconciled = !reconciled.error;
          }
        } catch (_) {
          console.warn("Creator revenue reconciliation pending for completed capture");
        }

        const result =
          Array.isArray(
            creditResult
          )
            ? creditResult[0]
            : creditResult;

        return jsonResponse(
          {
            success: true,

            paymentCompleted:
              true,

            orderId:
              data.id,

            captureId,

            status:
              data.status,

            packageId,

            coins:
              selected.coins,

            amount:
              capturedAmount,

            currency,

            credited:
              result?.credited ??
              false,

            newBalance:
              result?.new_balance ??
              null,
          }
        );
      }

      /* ======================================================
         UNKNOWN ACTION
      ====================================================== */

      return jsonResponse(
        {
          success: false,

          error:
            "Unknown action.",
        },
        400
      );
    } catch (error) {
      console.error(
        "Zynora PayPal function error:",
        error
      );

      return jsonResponse(
        {
          success: false,

          error:
            error instanceof Error
              ? error.message
              : "Unexpected server error.",
        },
        500
      );
    }
  }
);
