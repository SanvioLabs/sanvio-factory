<?php

class PatternController
{
    public function store($request)
    {
        // ruleid: api-security.identity-from-request.php
        $user = $request->input('user_id');
        // ruleid: api-security.identity-from-request.php
        $owner = $request->query('userId');
        // ruleid: api-security.identity-from-request.php
        $device = $_POST['device_id'];
        // ruleid: api-security.identity-from-request.php
        $acct = $request->header('x-account-id');
        // ok: api-security.identity-from-request.php
        $text = $request->input('text');
        // ok: api-security.identity-from-request.php
        $me = $request->user()->id;
        return [$user, $owner, $device, $acct, $text, $me];
    }
}
