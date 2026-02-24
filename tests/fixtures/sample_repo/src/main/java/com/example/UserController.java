package com.example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

// REST controller for user operations
@RestController
public class UserController {

    @GetMapping("/users")
    public String getUsers() {
        return "users";
    }

    @GetMapping("/users/{id}")
    public String getUser() {
        return "user";
    }
}
